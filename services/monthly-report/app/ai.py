"""AI responsibilities only: understand/classify one photo, and write the report narrative.

Every model answer is parsed defensively and normalised against the project's allowed values,
so a bad or partial answer never crashes the workflow and never introduces invented values.
"""

import base64
import io
import json
import re
from datetime import date

import httpx
from PIL import Image, ImageOps

from . import config

STAGES = ['BEFORE', 'DURING', 'AFTER']


class ModelError(RuntimeError):
    """The model could not be reached or gave no usable answer."""


def image_data_url(path: str, max_side: int = config.MODEL_IMAGE_SIZE) -> str:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=85)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


async def complete(messages: list[dict], auth: str, *, json_mode: bool = True) -> str:
    """Call this project's custom model through Biz GPT's OpenAI-compatible endpoint."""
    body = {'model': config.MODEL, 'stream': False, 'temperature': 0, 'messages': messages}
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    token = config.OPENWEBUI_API_KEY or auth
    try:
        async with httpx.AsyncClient(timeout=config.MODEL_TIMEOUT) as client:
            resp = await client.post(
                f'{config.OPENWEBUI_URL}/api/chat/completions', json=body, headers={'Authorization': f'Bearer {token}'}
            )
    except httpx.TimeoutException as e:
        raise ModelError(f'model {config.MODEL} timed out after {config.MODEL_TIMEOUT:.0f}s') from e
    except httpx.HTTPError as e:
        raise ModelError(f'model {config.MODEL} is unavailable ({type(e).__name__})') from e
    if resp.status_code >= 400:
        detail = resp.text[:200]
        try:
            detail = resp.json().get('detail') or detail
        except ValueError:
            pass
        raise ModelError(f'model {config.MODEL} failed: {resp.status_code} {detail}')
    try:
        content = resp.json()['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ModelError('model returned an unexpected response') from e
    if not isinstance(content, str) or not content.strip():
        raise ModelError('model returned an empty answer')
    return content


def parse_json(text: str) -> dict:
    """First JSON object in the text (models sometimes wrap it in prose or code fences)."""
    text = re.sub(r'```(?:json)?', '', text)
    start = text.find('{')
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:i + 1])
                    except ValueError:
                        break
                    if isinstance(value, dict):
                        return value
                    break
        start = text.find('{', start + 1)
    raise ModelError('model answer was not valid JSON')


# ------------------------------------------------------------------ photo analysis
CONDITIONS = ['untidy', 'mixed', 'tidy']


def photo_prompt(work_types: list[str]) -> str:
    # Observations first, decision last: small vision models classify far better this way.
    # Location and date are NOT asked for; the application reads them from visible_text.
    return (
        'You are checking ONE maintenance site photo. Look carefully, describe first, decide last.\n\n'
        'Fill this JSON:\n'
        '- "visible_text": every word and number printed in the photo (signboards, timestamp stamps), copied exactly. '
        '"" if there is none. Do not invent text.\n'
        '- "scene": one factual sentence of what is visible.\n'
        '- "people_working": true only if a person is visible in the photo.\n'
        '- "tools_or_machines": true only if a tool, machine, bin or equipment is visible.\n'
        '- "condition": "untidy" (overgrown, dirty, blocked, damaged, fallen), "mixed" (part done, part untidy) '
        'or "tidy" (neat, short, clean, clear, repaired).\n'
        '- "stage": "BEFORE" if condition is untidy and nobody is working; "DURING" if people are working or the area '
        'is part done; "AFTER" if condition is tidy and nobody is working; "UNKNOWN" if you cannot tell.\n'
        '- "stage_confidence": 0-100.\n'
        f'- "work_type": the maintenance work this photo is about, one of: {", ".join(work_types)}. null if unclear.\n'
        '- "work_type_confidence": 0-100.\n'
        '- "issues": problems actually visible (list of short strings), [] if none.\n\n'
        'Answer with the JSON object only:\n'
        '{"visible_text": "", "scene": "", "people_working": false, "tools_or_machines": false, "condition": "", '
        '"stage": "", "stage_confidence": 0, "work_type": null, "work_type_confidence": 0, "issues": []}'
    )


def _conf(value) -> int:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0
    if 0 < n <= 1:  # some models answer 0.87 instead of 87
        n *= 100
    return int(max(0, min(100, round(n))))


def _match(value, allowed: list[str]) -> str | None:
    if not isinstance(value, str):
        return None
    norm = re.sub(r'[^a-z0-9]', '', value.lower())
    if not norm or norm in ('unknown', 'null', 'none', 'na'):
        return None
    for option in allowed:
        if re.sub(r'[^a-z0-9]', '', option.lower()) == norm:
            return option
    return None


def _bool(value) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in ('true', 'yes'))


def find_location(text: str, zones: list[str]) -> tuple[str | None, str | None]:
    """Zone named in the photo's printed text (application rule, never guessed). (zone, evidence line)."""
    found = {}
    for line in (text or '').splitlines():
        flat = ' ' + re.sub(r'[^a-z0-9]+', ' ', line.lower()) + ' '
        for zone in zones:
            if ' ' + re.sub(r'[^a-z0-9]+', ' ', zone.lower()).strip() + ' ' in flat:
                found.setdefault(zone, line.strip()[:120])
    if len(found) == 1:
        return next(iter(found.items()))
    return None, None  # none, or conflicting zones in one photo


DATE_RE = re.compile(r'\b(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})(?:[ T,]+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp][Mm])?))?')


def find_datetime(text: str) -> str | None:
    m = DATE_RE.search(text or '')
    return ' '.join(g for g in m.groups() if g) if m else None


def normalise_photo(raw: dict, project: dict, work_types: list[str]) -> dict:
    """Clamp a model answer to allowed values; anything not allowed becomes Unknown (null)."""
    stage = str(raw.get('stage') or '').strip().upper()
    stage = stage if stage in STAGES else None
    stage_conf = _conf(raw.get('stage_confidence')) if stage else 0
    people, tools = _bool(raw.get('people_working')), _bool(raw.get('tools_or_machines'))
    condition = str(raw.get('condition') or '').strip().lower()
    condition = condition if condition in CONDITIONS else None

    # Consistency check: when the model's own observations contradict its stage, trust it less.
    conflicts = []
    if stage == 'DURING' and not (people or tools or condition == 'mixed'):
        conflicts.append('no people, tools or part-done work seen')
    if stage in ('BEFORE', 'AFTER') and people:
        conflicts.append('a person is working in the photo')
    if stage == 'BEFORE' and condition == 'tidy':
        conflicts.append('the area looks tidy')
    if stage == 'AFTER' and condition == 'untidy':
        conflicts.append('the area looks untidy')
    if conflicts:
        stage_conf = min(stage_conf, 50)

    visible_text = str(raw.get('visible_text') or '').strip()[:500]
    location, evidence = find_location(visible_text, project['zones'])
    work_type = _match(raw.get('work_type'), work_types)
    issues = raw.get('issues') or []
    if isinstance(issues, str):
        issues = [issues]
    issues = [str(i).strip()[:200] for i in issues if str(i).strip() and str(i).strip().lower() not in ('none', 'none detected', 'n/a')][:8]
    return {
        'stage': stage,
        'stage_confidence': stage_conf,
        'stage_conflicts': conflicts,
        'location': location,
        'location_confidence': 95 if location else 0,
        'location_evidence': evidence,
        'work_type': work_type,
        'work_type_confidence': _conf(raw.get('work_type_confidence')) if work_type else 0,
        'datetime_text': find_datetime(visible_text),
        'visible_text': visible_text,
        'observations': {'people_working': people, 'tools_or_machines': tools, 'condition': condition},
        'issues': issues,
        'description': str(raw.get('scene') or raw.get('description') or '').strip()[:400],
    }


async def analyse_photo(path: str, project: dict, work_types: list[str], auth: str) -> dict:
    messages = [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': photo_prompt(work_types)},
                {'type': 'image_url', 'image_url': {'url': image_data_url(path)}},
            ],
        }
    ]
    return normalise_photo(parse_json(await complete(messages, auth)), project, work_types)


# ------------------------------------------------------------------ report narrative
NARRATIVE_KEYS = ['executive_summary', 'location_summary', 'work_performed', 'issues_observations', 'remarks']


def report_prompt(facts: dict) -> str:
    return (
        'Write the narrative sections of a MONTHLY MAINTENANCE REPORT from the verified facts below.\n'
        'Use ONLY these facts. Do not add locations, work, dates, quantities or issues that are not listed. '
        'If something is missing, say it is missing. Plain professional English, no markdown headings.\n\n'
        f'FACTS (JSON):\n{json.dumps(facts, indent=1)}\n\n'
        'Return ONLY this JSON (each value is plain text, 1-4 short paragraphs or "- " bullet lines):\n'
        '{"executive_summary": "", "location_summary": "", "work_performed": "", "issues_observations": "", "remarks": ""}'
    )


async def write_report(facts: dict, auth: str) -> dict:
    raw = parse_json(await complete([{'role': 'user', 'content': report_prompt(facts)}], auth))
    out = {}
    for key in NARRATIVE_KEYS:
        value = raw.get(key)
        if isinstance(value, list):
            value = '\n'.join(f'- {v}' for v in value)
        out[key] = str(value).strip()[:4000] if value else ''
    if not any(out.values()):
        raise ModelError('model returned an empty report')
    return out


# ------------------------------------------------------------------ chat: understand a coordinator message
ACTIONS = ['start', 'gmail_import', 'update_photos', 'process', 'generate', 'set_text', 'reject', 'approve', 'status', 'help']
SECTION_NAMES = {'executive_summary': 'Executive Summary', 'location_summary': 'Location Summary',
                 'work_performed': 'Work Performed', 'issues_observations': 'Issues / Observations', 'remarks': 'Remarks'}


def interpret_prompt(text: str, cfg: dict, report: dict | None, filenames: list[str], zones: list[str]) -> str:
    projects = ', '.join(f'"{p["name"]}" (id {p["id"]})' for p in cfg['projects'])
    context = (
        f'Current report: {report["id"]}, project {report["project_id"]}, month {report["month"]}, status {report["status"]}.\n'
        f'Photo file names: {", ".join(filenames) or "none"}.\nLocations: {", ".join(zones)}.\n'
        if report else 'There is no report yet in this chat.\n'
    )
    return (
        'A maintenance coordinator wrote a chat message about a monthly photo report. Turn it into ONE action.\n'
        f'Today is {date.today():%Y-%m-%d}; a month written without a year means that month of the current year.\n'
        f'{context}Projects: {projects}.\nStages: BEFORE, DURING, AFTER. Work types: {", ".join(cfg["work_types"])}.\n'
        f'Report text sections: {", ".join(SECTION_NAMES)}.\n\n'
        'Actions:\n'
        '- "start": create or prepare a monthly report, e.g. "generate the October month report", "Taman Park October report" '
        '(when there is no report in this chat). Fill "project" (project id) and "month" (YYYY-MM) only if the message says them.\n'
        '- "gmail_import": fetch the site photos from Gmail / email / the mailbox (e.g. "get the photos from Gmail"). '
        'Fill "project" and "month" only if the message says them.\n'
        '- "update_photos": correct photos. "changes" = list of {"photo": file name as written, "stage", "location", '
        '"work_type", "exclude": true/false}; leave out what the message does not change.\n'
        '- "process": analyse the photos. "generate": write the report. "set_text": replace a section; "section" and "text".\n'
        '- "reject" with "reason" ONLY if the message uses the word reject. "approve" ONLY if the message says approve.\n'
        '- "status": show / open / continue an existing report, e.g. "show the October report". Fill "project" and "month" '
        'only if the message says them. "help": anything else.\n'
        'Examples: "change the remarks to: X" -> {"action": "set_text", "section": "remarks", "text": "X"}; '
        '"IMG_0103 is during" -> update_photos; "0104 is grass cutting" -> update_photos; "write the report" -> generate.\n\n'
        f'Message: """{text}"""\n\n'
        'Return ONLY JSON: {"action": "", "project": null, "month": null, "changes": [], "section": null, "text": null, "reason": null}'
    )


def _photo_by_name(name, photos: list[dict]) -> dict | None:
    if not isinstance(name, str) or not name.strip():
        return None
    key = re.sub(r'\.(jpe?g|png|webp)$', '', name.strip().lower())
    exact = [p for p in photos if re.sub(r'\.(jpe?g|png|webp)$', '', p['filename'].lower()) == key]
    if exact:
        return exact[0]
    partial = [p for p in photos if key and key in p['filename'].lower()]  # "0103" -> IMG_0103.jpg
    return partial[0] if len(partial) == 1 else None


SET_TEXT_RE = re.compile(r'\b(?:change|set|update|replace|make)\s+(?:the\s+)?([a-z /]+?)\s+(?:to|as)\s*:?\s*(.+)', re.I | re.S)


def normalise_intent(raw: dict, cfg: dict, photos: list[dict], zones: list[str], text: str = '') -> dict:
    """Validate the model's action against the project; anything unknown is dropped, never invented."""
    action = str(raw.get('action') or '').strip().lower()
    action = action if action in ACTIONS else 'help'
    # Decisions are never inferred: the coordinator has to say the word (application rule, not the model's call).
    if action == 'approve' and not re.search(r'\bapprov', text, re.I):
        action = 'help'
    if action == 'reject' and not re.search(r'\breject', text, re.I):
        action = 'help'
    # "change the remarks to: ..." is unambiguous; take it verbatim instead of trusting a paraphrase.
    m = SET_TEXT_RE.search(text or '')
    if m and action in ('help', 'set_text', 'reject', 'approve'):
        wanted = m.group(1).strip().lower().replace(' ', '_').replace('/', '')
        section = next((k for k, v in SECTION_NAMES.items() if wanted in (k, v.lower().replace(' ', '_').replace('/', ''))
                        or wanted.rstrip('s') == k.rstrip('s')), None)
        if section:
            return {'action': 'set_text', 'section': section, 'text': m.group(2).strip()[:4000]}
    out: dict = {'action': action}
    if action in ('start', 'gmail_import', 'status', 'generate'):
        # Only what the coordinator actually wrote; otherwise the chat asks with a form.
        project = resolve_project(raw.get('project'), text, cfg['projects'])
        out['project_id'] = project['id'] if project else None
        out['month'] = resolve_month(raw.get('month'), text)
    elif action == 'update_photos':
        changes, unknown = [], []
        # The model sometimes fills fields the message never mentions; keep only what was actually said.
        says_stage = bool(re.search(r'\b(before|during|after|in progress|pre|post)\b', text or '', re.I))
        says_exclude = bool(re.search(r'\b(exclud\w*|includ\w*|remove|drop|skip|ignore)\b', text or '', re.I))
        for c in raw.get('changes') or []:
            if not isinstance(c, dict):
                continue
            photo = _photo_by_name(c.get('photo'), photos)
            if not photo:
                unknown.append(str(c.get('photo')))
                continue
            change = {'photo_id': photo['id'], 'filename': photo['filename']}
            stage = str(c.get('stage') or '').upper()
            if stage in STAGES and says_stage:
                change['stage'] = stage
            if (loc := _match(c.get('location'), zones)):
                change['location'] = loc
            if (work := _match(c.get('work_type'), cfg['work_types'])):
                change['work_type'] = work
            if isinstance(c.get('exclude'), bool) and says_exclude:
                change['exclude'] = c['exclude']
            if len(change) > 2:
                changes.append(change)
        out.update(changes=changes, unknown_photos=unknown)
        if not changes:
            out['action'] = 'help'
    elif action == 'set_text':
        section = str(raw.get('section') or '').strip().lower().replace(' ', '_').replace('/', '')
        section = next((k for k, v in SECTION_NAMES.items() if section in (k, v.lower().replace(' ', '_'))), None)
        text = str(raw.get('text') or '').strip()
        if section and text:
            out.update(section=section, text=text[:4000])
        else:
            out['action'] = 'help'
    elif action == 'reject':
        out['reason'] = str(raw.get('reason') or '').strip()[:1000] or None
    return out


# ------------------------------------------------------------------ Gmail: understand a site-photo email
def email_prompt(email: dict, cfg: dict) -> str:
    projects = ', '.join(f'"{p["name"]}" (id {p["id"]})' for p in cfg['projects'])
    names = ', '.join(a['filename'] for a in email['images'][:30])
    return (
        'An email with photo attachments arrived in the maintenance reports mailbox. Decide if it sends site photos '
        'for a monthly maintenance report, and for which project and month.\n'
        f'Projects: {projects}.\n\n'
        f'From: {email["from"]}\nDate: {email["date"]}\nSubject: {email["subject"]}\nAttachments: {names}\n'
        f'Body:\n"""{email["body"][:2000]}"""\n\n'
        'Use only what the email says. "project": the project id, or null if the email does not name one. '
        '"month": YYYY-MM only if the email names the month (e.g. "September 2026", "Sept photos" with a year from the date); '
        'otherwise null. Do not guess.\n'
        'Return ONLY JSON: {"is_site_photos": true, "project": null, "month": null}'
    )


MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']


def project_named_in(text: str, project: dict) -> bool:
    """The email itself names the project: its id, full name, or the distinctive first word of the name."""
    flat = ' ' + re.sub(r'[^a-z0-9]+', ' ', text.lower()) + ' '
    first = re.sub(r'[^a-z0-9]+', ' ', project['name'].lower()).split()[0]
    keys = {re.sub(r'[^a-z0-9]+', ' ', project['id'].lower()).strip(), re.sub(r'[^a-z0-9]+', ' ', project['name'].lower()).strip()}
    if len(first) >= 4:
        keys.add(first)
    return any(f' {k} ' in flat for k in keys)


def month_named_in(text: str, month: str) -> bool:
    """The email itself names the month (e.g. "September", "Sep 2026", "2026-09", "09/2026")."""
    y, m = month.split('-')
    name = MONTHS[int(m) - 1]
    low = text.lower()
    return bool(re.search(rf'\b({name}|{name[:3]})\b', low) or f'{y}-{m}' in low or re.search(rf'\b0?{int(m)}\s*/\s*{y}\b', low))


def find_project_in(text: str, projects: list[dict]) -> dict | None:
    """The one project the text names, or None when it names none or several."""
    named = [p for p in projects if project_named_in(text, p)]
    return named[0] if len(named) == 1 else None


def find_month_in(text: str) -> str | None:
    """The one month the text names with its year ("September 2026", "Sep 2026", "2026-09", "09/2026")."""
    low = text.lower()
    found = set()
    for i, name in enumerate(MONTHS, 1):
        for m in re.finditer(rf'\b(?:{name}|{name[:3]})\.?,?\s+(\d{{4}})\b', low):
            found.add(f'{m.group(1)}-{i:02d}')
    found |= {f'{y}-{int(mo):02d}' for y, mo in re.findall(r'\b(\d{4})-(0[1-9]|1[0-2])\b', low)}
    found |= {f'{y}-{int(mo):02d}' for mo, y in re.findall(r'\b(0?[1-9]|1[0-2])\s*/\s*(\d{4})\b', low)}
    return found.pop() if len(found) == 1 else None


def resolve_project(value, text: str, projects: list[dict]) -> dict | None:
    """Model's project if the text supports it, else the one project the text itself names."""
    wanted = re.sub(r'[^a-z0-9]+', ' ', str(value or '').lower()).strip()
    for p in projects:
        keys = {re.sub(r'[^a-z0-9]+', ' ', p['id'].lower()).strip(), re.sub(r'[^a-z0-9]+', ' ', p['name'].lower()).strip()}
        if wanted and (wanted in keys or any(k.startswith(wanted) for k in keys if len(wanted) >= 4)):
            if not text or project_named_in(text, p):
                return p
    return find_project_in(text, projects) if text else None


def resolve_month(value, text: str) -> str | None:
    m = re.fullmatch(r'(\d{4})-(\d{1,2})', str(value or '').strip())
    month = f'{m.group(1)}-{int(m.group(2)):02d}' if m and 1 <= int(m.group(2)) <= 12 else None
    if month and (not text or month_named_in(text, month)):
        return month
    return find_month_in(text) if text else None


def normalise_email(raw: dict, cfg: dict, email_text: str = '') -> dict:
    """Keep the model's project/month only when the email really states them (application check, never a guess)."""
    project = resolve_project(raw.get('project'), email_text, cfg['projects'])
    month = resolve_month(raw.get('month'), email_text)
    return {
        'is_site_photos': raw.get('is_site_photos') is not False,
        'project_id': project['id'] if project else None,
        'month': month,
    }
