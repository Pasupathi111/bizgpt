"""
title: Monthly Report
author: Biz GPT
description: AI-Assisted Monthly Report Delivery inside the chat. Attach site photos and say the project and month; the Monthly Report Vision model analyses them, and dynamic in-chat forms let you review, correct, generate, reject or approve the report and download the PDF.
version: 0.1.0
"""

# Installed in Biz GPT as Workspace -> Functions -> "Monthly Report" (a Pipe, so it appears in the chat
# model picker). All state, rules and model calls live in services/monthly-report; this pipe only moves
# chat messages and photos to that service and renders its answers as interactive cards.

import asyncio
import base64
import copy
import html
import json
import re
from typing import Optional

import aiohttp
from pydantic import BaseModel, Field

STAGES = ['BEFORE', 'DURING', 'AFTER']
SECTIONS = [
    ('executive_summary', 'Executive Summary'),
    ('location_summary', 'Location Summary'),
    ('work_performed', 'Work Performed'),
    ('issues_observations', 'Issues / Observations'),
    ('remarks', 'Remarks'),
]
TASK_REPLIES = {
    'title_generation': json.dumps({'title': '📋 Monthly Report'}),
    'tags_generation': json.dumps({'tags': ['Monthly Report']}),
    'follow_up_generation': json.dumps({'follow_ups': []}),
}
CMD_RE = re.compile(r'```mr\s*(\{.*?\})\s*```', re.S)
# Biz GPT prepends an <attached_files> list to the message text; it is not the user's words.
ATTACHED_RE = re.compile(r'<attached_files>.*?</attached_files>', re.S)
REPORT_RE = re.compile(r'\bMR-[A-Z0-9]{4,12}\b')
HELP = (
    'I build the **monthly maintenance photo report** with you, step by step:\n\n'
    '1. Attach the site photos and say the project and month, e.g. *"September 2026 report for Taman Park"*, '
    'or say *"get the photos from Gmail"* and I will fetch the site-photo emails from the reports mailbox.\n'
    '2. I analyse every photo (Before / During / After, location, work, date, issues, confidence) and show a review form.\n'
    '3. Correct anything in the form (or just tell me, e.g. *"IMG_0103 is during"*), then generate the report.\n'
    '4. Edit the report text in the form, then **Approve** (or Reject). You get the PDF.\n\n'
    'AI assists; nothing is final until you approve it.'
)


class ServiceError(Exception):
    pass


class Pipe:
    class Valves(BaseModel):
        SERVICE_URL: str = Field(
            default='http://bizgpt-monthly-report:8000',
            description='Monthly Report service URL as seen from the Biz GPT server',
        )
        LINK_BASE: str = Field(
            default='/api/v1/bizgpt/monthly-report',
            description="Path the user's browser uses to reach the service (for the PDF links)",
        )
        PAGE_PATH: str = Field(default='/monthly-report', description='Monthly Report page in Biz GPT')
        BIZGPT_INTERNAL_URL: str = Field(
            default='http://127.0.0.1:8080', description='Biz GPT API as seen from inside Biz GPT (to read photo file names)'
        )

    def __init__(self):
        self.valves = self.Valves()
        self.name = 'Monthly Report'

    # ------------------------------------------------------------------ entry point
    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __request__=None,
        __event_emitter__=None,
        __task__: Optional[str] = None,
        __chat_id__: Optional[str] = None,
    ):
        if __task__:  # Biz GPT background tasks (chat title, tags, follow-ups): answer without touching reports.
            return TASK_REPLIES.get(__task__, '')
        # Biz GPT shares one Pipe instance between all chats: keep this request's emitter, embeds and session on
        # its own copy, or two chats running at once send each other's progress and cards to the wrong chat.
        return await copy.copy(self)._handle(body, __request__, __event_emitter__, __chat_id__)

    async def _handle(self, body: dict, __request__, __event_emitter__, __chat_id__: Optional[str]):
        self.emit = __event_emitter__
        self.embeds = []
        self.auth = self._auth(__request__)
        if not self.auth:
            return 'Please sign in to Biz GPT again; I could not read your session.'

        messages = body.get('messages') or []
        last = messages[-1] if messages else {'content': ''}
        text, images = self._split(last.get('content'))
        # Biz GPT turns attached photos into image parts and drops their file names; read them back from the chat.
        self.names = await self._image_names(__chat_id__)
        images = self._name_images(images, self.names[-1] if self.names else [])
        cmd = self._command(text)
        report_id = (cmd or {}).get('report') or self._report_in_history(messages[:-1])

        try:
            if cmd:
                return await self._run(cmd, report_id, messages)
            if images and report_id and await self._editable(report_id):
                return await self._add_photos_and_process(report_id, images)
            if not text.strip() and not images:
                return HELP
            intent = await self._api('POST', '/api/interpret', {'text': text or 'start a report', 'report_id': report_id})
            if images and not report_id:
                intent['action'] = 'start'
            return await self._run(intent, report_id, messages, images=images)
        except ServiceError as e:
            await self._status(f'Stopped: {e}', done=True)
            return f'⚠️ {e}'

    # ------------------------------------------------------------------ actions
    async def _run(self, cmd: dict, report_id: Optional[str], messages: list, images: Optional[list] = None) -> str:
        action = cmd.get('action')
        if action == 'gmail_import':
            return await self._gmail_import(cmd.get('project_id'), cmd.get('month'))

        project_id, month = cmd.get('project_id'), cmd.get('month')
        if action == 'start' and report_id and not (project_id or month or images):
            action = 'generate'  # "generate the report" inside a report's chat means this report
        if action == 'start' or (action in ('status', 'generate') and not report_id and (project_id or month)):
            return await self._report_for(project_id, month, messages, images)

        if action == 'status' and not report_id:
            found = await self._latest_report()
            if not found:
                return ('There is no report yet. Say e.g. *"generate the October month report"*, or attach the site photos here.')
            return await self._continue_report(found)

        if not report_id:
            return HELP

        if action == 'delete_report':
            try:
                report = await self._api('GET', f'/api/reports/{report_id}')
            except ServiceError:
                return (f'Report {report_id} was already deleted. Say e.g. *"Generate the October month report"* to start the '
                        'month fresh, or *"show me the October month report"* to open the current one.')
            await self._api('DELETE', f'/api/reports/{report_id}')
            label = month_label(report['month'])
            return (f'🗑 **{label}** report {report_id} deleted: photos, PDF and month folder removed, and its Gmail email can be '
                    f'imported again. Say *"Generate the {label.split()[0]} month report"* to start fresh.')
        if action == 'process':
            return await self._process(report_id)
        if action == 'update_photos':
            for change in cmd.get('changes') or []:
                await self._apply_change(report_id, change)
            note = ''
            if cmd.get('unknown_photos'):
                note = f"\n\nI could not find these photos: {', '.join(cmd['unknown_photos'])}."
            if cmd.get('then') == 'generate':
                return await self._generate(report_id)
            return await self._show_review(report_id, 'Saved your corrections.' + note)
        if action == 'generate':
            return await self._generate(report_id)
        if action == 'save_draft':
            await self._save(report_id, cmd)
            return await self._show_report(report_id, 'Draft saved.')
        if action == 'set_text':
            await self._api('PUT', f'/api/reports/{report_id}/draft', {'sections': {cmd['section']: cmd['text']}})
            return await self._show_report(report_id, 'Updated the report text.')
        if action == 'reject':
            if not cmd.get('reason'):
                return 'Tell me why the report is rejected, e.g. *"reject: the summary misses the Zone B photo gap"*.'
            await self._save(report_id, cmd)
            await self._api('POST', f'/api/reports/{report_id}/reject', {'reason': cmd['reason']})
            return await self._show_report(report_id, 'Report rejected. Correct it below and click **Save draft** to send it back for review.')
        if action == 'approve':
            await self._save(report_id, cmd)
            current = await self._api('GET', f'/api/reports/{report_id}')
            flagged = current['needs_review'] if current['status'] == 'in_review' else 0
            if flagged and not cmd.get('confirm_flagged'):
                return await self._show_report(report_id, f'{flagged} photo(s) are still flagged for review. Click **Approve** in the '
                                                          'report and then **Confirm photos & approve**, or correct them first.')
            report = await self._api('POST', f'/api/reports/{report_id}/approve',
                                     {'confirm_flagged': bool(cmd.get('confirm_flagged'))})
            return await self._show_approved(report)
        if action == 'status':
            report = await self._api('GET', f'/api/reports/{report_id}')
            if report['status'] == 'approved':
                return await self._show_approved(report)
            if report.get('content'):
                return await self._show_report(report_id)
            return await self._show_review(report_id)
        return HELP

    async def _add_photos_and_process(self, report_id: str, images: list) -> str:
        await self._status(f'Uploading {len(images)} photo(s) to report {report_id}…')
        form = aiohttp.FormData()
        for name, data in images:
            form.add_field('files', data, filename=name, content_type='image/jpeg')
        result = await self._api('POST', f'/api/reports/{report_id}/photos', form=form)
        rejected = ''.join(f"\n- {r['filename']}: {r['reason']}" for r in result.get('rejected', []))
        if rejected:
            await self._status(f'Some files were skipped: {rejected}')
        return await self._process(report_id, extra=('Skipped files:' + rejected) if rejected else '')

    async def _gmail_import(self, project_id: Optional[str], month: Optional[str]) -> str:
        await self._status('🔄 Syncing with Gmail…')
        result = await self._api('POST', '/api/gmail/import', {'project_id': project_id, 'month': month})
        lines = []
        for i in result['imported']:
            fails = f" ({len(i['failed'])} skipped)" if i['failed'] else ''
            lines.append(f"📥 **{i['subject']}** from {i['from']}: {i['added']} photo(s) → report {i['report_id']}{fails}")
        for n in result['needs_info']:
            lines.append(f"❓ **{n['subject']}** ({n['photos']} photo(s)): the email does not say the project and month.")
        if result['needs_info']:
            cfg = await self._api('GET', '/api/config')
            await self._embed(setup_card(cfg, project_id, month, action='gmail_import',
                                         note='Choose the project and month for the emails above, then import them.',
                                         button='Import these photos'))
        if not result['imported']:
            await self._status('No new photos imported', done=True)
            if not result['needs_info']:
                existing = await (self._find_report(project_id, month) if (project_id or month) else self._latest_gmail_report())
                if existing:
                    return await self._continue_report(
                        existing, f"No new site-photo emails in **{result['mailbox']}**; continuing **Report {existing}** "
                                  'with the photos already imported.')
                return f"No new site-photo emails in **{result['mailbox']}**. Send the photos there (subject e.g. *\"Taman Park September 2026 photos\"*) and ask me again."
            return '\n\n'.join(lines)
        report_id = result['reports'][0] if result['reports'] else result['imported'][0]['report_id']
        more = [r for r in result['reports'][1:]]
        if more:
            lines.append('Other reports updated: ' + ', '.join(more) + ' (say *"show report MR-…"* to open one).')
        return await self._wait_and_review(report_id, '\n\n'.join(lines))

    async def _report_for(self, project_id: Optional[str], month: Optional[str], messages: list,
                          images: Optional[list]) -> str:
        """The user asked for a month's report: continue it if it exists, else fetch that month's photos from Gmail."""
        photos = images if images is not None else self._all_images(messages)
        no_mail = ''
        existing = await self._find_report(project_id, month) if month else None
        if existing:
            if photos and await self._editable(existing):
                return await self._add_photos_and_process(existing, photos)
            return await self._continue_report(existing, f'**Report {existing}** for {month_label(month)} already exists; continuing it.')
        if not photos and month:
            # Emails keep the project/month they state themselves, so another month's photos never land here.
            await self._status(f'🔄 Syncing with Gmail for {month_label(month)} site photos…')
            result = await self._api('POST', '/api/gmail/import', {'only_month': month})
            found = await self._find_report(project_id, month)
            if found:
                lines = [f"📥 **{i['subject']}** from {i['from']}: {i['added']} photo(s) → report {i['report_id']}"
                         for i in result['imported'] if i['report_id'] == found]
                return await self._wait_and_review(found, '\n\n'.join(lines))
            await self._status(f'No {month_label(month)} photos in Gmail', done=True)
            no_mail = (f'No new {month_label(month)} site-photo email was found in **{result["mailbox"]}** (check the address '
                       'is exactly this one and the email is not in Trash).')
        if not (project_id and month):
            cfg = await self._api('GET', '/api/config')
            await self._embed(setup_card(cfg, project_id, month))
            return 'Choose the **project** and **month** in the form above and click **Start report**. I will analyse the photos you attached.'
        reports = (await self._api('GET', '/api/reports'))['reports']
        empty = next((r for r in reports if r['project_id'] == project_id and r['month'] == month
                      and r['status'] == 'draft' and not r.get('photo_count')), None)
        report = (await self._api('GET', f"/api/reports/{empty['id']}") if empty
                  else await self._api('POST', '/api/reports', {'project_id': project_id, 'month': month}))
        if not photos:
            return (f'**Report {report["id"]}** is ready for {report["project"]["name"]}, {month_label(month)}.\n\n'
                    + no_mail +
                    ' Attach the photos in your next message, or email them there and ask me again.')
        return await self._add_photos_and_process(report['id'], photos)

    async def _find_report(self, project_id: Optional[str], month: Optional[str]) -> Optional[str]:
        """The month's report to continue: an approved one first, then the one furthest along, newest first.
        Empty reports (no photos yet) never count, so asking for the month syncs Gmail instead of opening them."""
        reports = (await self._api('GET', '/api/reports'))['reports']
        match = [r for r in reports if r.get('photo_count') and (not month or r['month'] == month)
                 and (not project_id or r['project_id'] == project_id)]
        rank = {'approved': 4, 'in_review': 3, 'rejected': 3, 'analyzed': 2, 'processing': 1}
        match.sort(key=lambda r: (rank.get(r['status'], 0), r.get('updated_at') or ''), reverse=True)
        return match[0]['id'] if match else None

    async def _latest_report(self) -> Optional[str]:
        return await self._find_report(None, None)

    async def _latest_gmail_report(self) -> Optional[str]:
        """The report the most recent Gmail import went into."""
        status = await self._api('GET', '/api/gmail/status')
        return next((r['report_id'] for r in status.get('recent', []) if r.get('status') == 'imported' and r.get('report_id')), None)

    async def _continue_report(self, report_id: str, note: str = '') -> str:
        """Show a report at the step it has reached, so the flow continues from there."""
        report = await self._api('GET', f'/api/reports/{report_id}')
        if report['status'] == 'processing':
            return await self._wait_and_review(report_id, note)
        if report.get('content'):  # includes approved reports: the full report screen, read-only, with the PDF
            return await self._show_report(report_id, note)
        return await self._show_review(report_id, note)

    async def _process(self, report_id: str, extra: str = '') -> str:
        await self._api('POST', f'/api/reports/{report_id}/process')
        return await self._wait_and_review(report_id, extra)

    async def _wait_and_review(self, report_id: str, extra: str = '') -> str:
        report = await self._api('GET', f'/api/reports/{report_id}')
        model = report['model']
        while report['status'] == 'processing':
            p = report.get('progress') or {}
            await self._status(f'Analysing photos with {model}: {(p.get("done") or 0) + (p.get("failed") or 0)} / {p.get("total") or "?"}')
            await asyncio.sleep(2)
            report = await self._api('GET', f'/api/reports/{report_id}')
        p = report.get('progress') or {}
        await self._status(f'Analysed {p.get("done", 0)} photo(s), {p.get("failed", 0)} failed', done=True)
        return await self._show_review(report_id, extra)

    async def _apply_change(self, report_id: str, change: dict):
        body = {'fields_set': [f for f in ('stage', 'location', 'work_type') if f in change]}
        for f in body['fields_set']:
            body[f] = change[f] or None
        if 'exclude' in change:
            body['excluded'] = bool(change['exclude'])
        if 'reviewed' in change:
            body['reviewed'] = bool(change['reviewed'])
        if body['fields_set'] or 'excluded' in body or 'reviewed' in body:
            await self._api('PATCH', f'/api/reports/{report_id}/photos/{change["photo_id"]}', body)

    async def _generate(self, report_id: str) -> str:
        await self._status('Writing the report with Monthly Report Vision…')
        report = await self._api('POST', f'/api/reports/{report_id}/generate')
        await self._status('Report ready', done=True)
        if report['status'] == 'approved':  # same photos, same report: hand back the approved one
            return await self._continue_report(report_id, 'This report is already approved, so here it is again (same photos, same report).')
        return await self._show_report(report_id, 'Here is the AI draft. Edit anything, then **Approve** or **Reject**.')

    async def _save(self, report_id: str, cmd: dict):
        body = {}
        if isinstance(cmd.get('sections'), dict):
            body['sections'] = {k: str(v) for k, v in cmd['sections'].items() if k in dict(SECTIONS)}
        if isinstance(cmd.get('remarks'), str):
            body['remarks'] = cmd['remarks']
        if body:
            report = await self._api('GET', f'/api/reports/{report_id}')
            if report['status'] in ('draft', 'analyzed', 'in_review', 'rejected'):
                await self._api('PUT', f'/api/reports/{report_id}/draft', body)

    # ------------------------------------------------------------------ cards
    async def _show_review(self, report_id: str, note: str = '') -> str:
        report = await self._api('GET', f'/api/reports/{report_id}')
        thumbs = await self._api('GET', f'/api/reports/{report_id}/thumbs?size=120')
        await self._embed(review_card(report, thumbs))
        flagged = report['needs_review']
        lines = [f'**Report {report["id"]}** · {report["project"]["name"]} · {month_label(report["month"])}']
        if note:
            lines.append(note)
        lines.append(
            f'⚠️ {flagged} photo(s) need your review. Correct them in the form (or tell me), tick **Checked**, then save.'
            if flagged else '✅ All photos are reviewed. Click **Generate monthly report** in the form.'
        )
        if report['validation']['missing']:
            lines.append('Missing photos: ' + '; '.join(report['validation']['missing']) + '.')
        return '\n\n'.join(lines)

    async def _show_report(self, report_id: str, note: str = '') -> str:
        report = await self._api('GET', f'/api/reports/{report_id}')
        thumbs = await self._api('GET', f'/api/reports/{report_id}/thumbs?size=120')
        base = self.valves.LINK_BASE.rstrip('/')
        await self._embed(report_card(report, thumbs, base))
        lines = [f'**Report {report["id"]}** · {report["project"]["name"]} · {month_label(report["month"])} · status **{report["status"].replace("_", " ")}**']
        if note:
            lines.append(note)
        if report['approval_blockers'] and report['status'] == 'in_review':
            lines.append('Before approving: ' + '; '.join(report['approval_blockers']) + '. Click **Approve** and confirm them, '
                         'or say *"show photos"* to correct them first.')
        if report['status'] == 'approved':
            lines.append(f'[📄 View Report]({base}/reports/{report["id"]}/pdf) · '
                         f'[⬇️ Download PDF]({base}/reports/{report["id"]}/pdf?download=true) · '
                         f'[Open in Monthly Report]({self.valves.PAGE_PATH}?report={report["id"]}) · '
                         'say *"generate again"* any time: the same photos give the same report.')
        return '\n\n'.join(lines)

    async def _show_approved(self, report: dict) -> str:
        base = self.valves.LINK_BASE.rstrip('/')
        await self._embed(approved_card(report, base))
        return (
            f'**Report {report["id"]}** is approved and the PDF is ready: '
            f'[📄 View Report]({base}/reports/{report["id"]}/pdf) · '
            f'[⬇️ Download PDF]({base}/reports/{report["id"]}/pdf?download=true) · '
            f'[Open in Monthly Report]({self.valves.PAGE_PATH}?report={report["id"]})'
        )

    # ------------------------------------------------------------------ plumbing
    def _auth(self, request) -> str:
        if request is None:
            return ''
        header = request.headers.get('authorization') or ''
        if header.lower().startswith('bearer '):
            return header
        token = request.cookies.get('token') if hasattr(request, 'cookies') else None
        return f'Bearer {token}' if token else ''

    async def _api(self, method: str, path: str, body: Optional[dict] = None, form=None):
        url = self.valves.SERVICE_URL.rstrip('/') + path
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                async with session.request(method, url, json=body if form is None else None, data=form,
                                           headers={'Authorization': self.auth}) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status >= 400:
                        detail = data.get('detail') if isinstance(data, dict) else None
                        raise ServiceError(detail if isinstance(detail, str) else f'Monthly Report service error {resp.status}')
                    return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise ServiceError(f'The Monthly Report service is not reachable ({type(e).__name__})')

    async def _editable(self, report_id: str) -> bool:
        try:
            report = await self._api('GET', f'/api/reports/{report_id}')
        except ServiceError:
            return False
        return report['status'] in ('draft', 'analyzed', 'in_review', 'rejected')

    async def _status(self, description: str, done: bool = False):
        if self.emit:
            await self.emit({'type': 'status', 'data': {'description': description, 'done': done}})

    async def _embed(self, html_doc: str):
        # Each 'embeds' event replaces the message's embeds, so always send all of this reply's cards.
        self.embeds.append(html_doc)
        if self.emit:
            await self.emit({'type': 'embeds', 'data': {'embeds': list(self.embeds)}})

    @staticmethod
    def _split(content) -> tuple[str, list]:
        if isinstance(content, str):
            return ATTACHED_RE.sub('', content).strip(), []
        text, images = [], []
        for part in content or []:
            if part.get('type') == 'text':
                text.append(part.get('text') or '')
            elif part.get('type') in ('image_url', 'input_image'):
                url = part.get('image_url')
                url = url.get('url') if isinstance(url, dict) else url
                if isinstance(url, str) and url.startswith('data:image/'):
                    try:
                        images.append(base64.b64decode(url.split(',', 1)[1]))
                    except (IndexError, ValueError):
                        continue
        return ATTACHED_RE.sub('', '\n'.join(text)).strip(), images

    async def _image_names(self, chat_id: Optional[str]) -> list:
        """File names of the photos in each user message of this chat, oldest first."""
        if not chat_id or chat_id.startswith('local:'):
            return []
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f'{self.valves.BIZGPT_INTERNAL_URL.rstrip("/")}/api/v1/chats/{chat_id}',
                                       headers={'Authorization': self.auth}) as resp:
                    chat = (await resp.json(content_type=None)) if resp.status == 200 else {}
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return []
        history = (chat.get('chat') or {}).get('history') or {}
        by_id, node, chain = history.get('messages') or {}, history.get('currentId'), []
        while node and node in by_id:  # walk the current branch back to the start
            chain.append(by_id[node])
            node = by_id[node].get('parentId')
        out = []
        for m in reversed(chain):
            if m.get('role') == 'user':
                out.append([f.get('name') or '' for f in m.get('files') or []
                            if f.get('type') == 'image' or str(f.get('content_type') or '').startswith('image/')])
        return out

    @staticmethod
    def _name_images(images: list, names: list) -> list:
        return [(names[i] if i < len(names) and names[i] else f'photo-{i + 1}.jpg', data) for i, data in enumerate(images)]

    def _all_images(self, messages: list) -> list:
        out, turn = [], 0
        for m in messages:
            if m.get('role') == 'user':
                names = self.names[turn] if turn < len(self.names) else []
                out += self._name_images(self._split(m.get('content'))[1], names)
                turn += 1
        return out

    @staticmethod
    def _command(text: str) -> Optional[dict]:
        m = CMD_RE.search(text or '')
        if not m:
            return None
        try:
            cmd = json.loads(m.group(1))
        except ValueError:
            return None
        return cmd if isinstance(cmd, dict) and cmd.get('action') else None

    @staticmethod
    def _report_in_history(messages: list) -> Optional[str]:
        for m in reversed(messages):
            content = m.get('content')
            content = content if isinstance(content, str) else ' '.join(p.get('text', '') for p in content or [] if isinstance(p, dict))
            found = REPORT_RE.findall(content or '')
            if found:
                return found[-1]
        return None


# ====================================================================== HTML cards
def e(value) -> str:
    return html.escape('' if value is None else str(value))


def js(value) -> str:
    return json.dumps(value).replace('</', '<\\/')


def month_label(month: str) -> str:
    import calendar

    try:
        y, m = month.split('-')
        return f'{calendar.month_name[int(m)]} {y}'
    except (ValueError, IndexError):
        return month


CSS = """
:root { color-scheme: light dark; --fg:#0f172a; --muted:#64748b; --line:#e2e8f0; --card:#fff; --soft:#f8fafc;
  --ok:#059669; --warn:#d97706; --bad:#dc2626; --brand:#f97316; --human:#0284c7; }
@media (prefers-color-scheme: dark) { :root { --fg:#e2e8f0; --muted:#94a3b8; --line:#1e293b; --card:#0f172a; --soft:#111827; } }
* { box-sizing: border-box; } body { margin:0; font:13.5px/1.45 Inter, system-ui, sans-serif; color:var(--fg); background:transparent; }
.card { border:1px solid var(--line); border-radius:16px; background:var(--card); overflow:hidden; }
.head { padding:14px 16px; background:var(--soft); border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; }
.title { font-weight:700; font-size:15px; } .sub { color:var(--muted); font-size:12.5px; }
.body { padding:14px 16px; } .chips { display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; }
.chip { font-size:12px; padding:2px 8px; border-radius:999px; background:var(--soft); border:1px solid var(--line); }
.chip.ok { color:var(--ok); } .chip.warn { color:var(--warn); }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:10px; }
.tile { border:1px solid var(--line); border-radius:12px; overflow:hidden; display:flex; flex-direction:column; }
.tile.flag { border-color:#f59e0b; } .tile.excl { opacity:.5; }
.tile img { width:100%; height:120px; object-fit:cover; display:block; }
.tile .in { padding:8px 10px; display:flex; flex-direction:column; gap:4px; font-size:12.5px; }
.row { display:flex; justify-content:space-between; gap:6px; align-items:center; }
.k { color:var(--muted); } .ok { color:var(--ok); } .warn { color:var(--warn); } .human { color:var(--human); }
select, input, textarea { font:inherit; color:inherit; background:var(--card); border:1px solid var(--line); border-radius:8px; padding:4px 6px; width:100%; }
textarea { min-height:72px; resize:vertical; padding:8px; }
.reasons { background:#fffbeb; color:#92400e; border-radius:8px; padding:6px 8px; font-size:12px; }
@media (prefers-color-scheme: dark) { .reasons { background:#451a03; color:#fcd34d; } }
.two { display:grid; grid-template-columns: 1fr 260px; gap:12px; margin-top:12px; } @media (max-width:640px) { .two { grid-template-columns:1fr; } }
.panel { border:1px solid var(--line); border-radius:12px; padding:10px 12px; }
.zone { margin-bottom:8px; } .zone b { display:block; margin-bottom:2px; }
.thumbs { display:flex; gap:4px; flex-wrap:wrap; } .thumbs img { width:44px; height:44px; object-fit:cover; border-radius:6px; }
.miss { width:44px; height:44px; border:1px dashed #f59e0b; border-radius:6px; font-size:10px; color:var(--warn); display:flex; align-items:center; justify-content:center; }
.actions { display:flex; gap:8px; flex-wrap:wrap; align-items:center; padding:12px 16px; border-top:1px solid var(--line); background:var(--soft); }
button { border:0; border-radius:10px; padding:9px 16px; font:600 13.5px Inter, system-ui, sans-serif; cursor:pointer; }
button:disabled { opacity:.5; cursor:default; }
.primary { background:var(--brand); color:#fff; } .approve { background:#16a34a; color:#fff; } .reject { background:#fff; color:var(--bad); border:1px solid #fca5a5; }
.ghost { background:var(--card); color:var(--fg); border:1px solid var(--line); }
a.btn { display:inline-block; text-decoration:none; border-radius:10px; padding:9px 16px; font:600 13.5px Inter, system-ui, sans-serif; }
.note { font-size:12.5px; color:var(--muted); } .spacer { flex:1; }
h4 { margin:14px 0 4px; font-size:13.5px; } table { width:100%; border-collapse:collapse; font-size:12.5px; }
td, th { text-align:left; padding:4px 6px; border-top:1px solid var(--line); } th { color:var(--muted); font-weight:500; }
.banner { padding:8px 12px; border-radius:10px; margin-bottom:10px; } .banner.bad { background:#fef2f2; color:#991b1b; } .banner.good { background:#ecfdf5; color:#065f46; }
@media (prefers-color-scheme: dark) { .banner.bad { background:#450a0a; color:#fecaca; } .banner.good { background:#022c22; color:#a7f3d0; } }
"""

SCRIPT = """
const post = (m) => window.parent !== window && window.parent.postMessage(m, '*');
const height = () => post({ type: 'iframe:height', height: document.documentElement.scrollHeight });
new ResizeObserver(height).observe(document.body); height();
const fr = document.getElementById('fresh');
if (fr) {
  fr.onclick = () => { document.getElementById('freshcf').style.display = 'flex'; height(); };
  document.getElementById('freshno').onclick = () => { document.getElementById('freshcf').style.display = 'none'; height(); };
  document.getElementById('freshok').onclick = () => send('🗑 Delete the ' + fr.dataset.label + ' report ' + fr.dataset.rid + ' and start fresh',
    { action: 'delete_report', report: fr.dataset.rid });
}
const send = (label, cmd) => {
  document.querySelectorAll('button').forEach((b) => (b.disabled = true));
  const n = document.getElementById('note'); if (n) n.textContent = 'Sent to the chat. Confirm it in the Biz GPT dialog if asked.';
  post({ type: 'input:prompt:submit', text: label + '\\n```mr\\n' + JSON.stringify(cmd) + '\\n```' });
};
"""


def page(body: str, script: str = '') -> str:
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}<script>{SCRIPT}{script}</script></body></html>'


def conf_badge(eff: dict, field: str, threshold: int) -> str:
    if eff.get(f'{field}_source') == 'human':
        return '<span class="human">Human ✎</span>'
    if not eff.get(field):
        return '<span class="warn">— ⚠</span>'
    c = eff.get(f'{field}_confidence') or 0
    return f'<span class="{"ok" if c >= threshold else "warn"}">{c}% {"✓" if c >= threshold else "⚠"}</span>'


def options(values: list, selected, unknown: str = 'Unknown') -> str:
    opts = [f'<option value="">{e(unknown)}</option>']
    opts += [f'<option value="{e(v)}"{" selected" if v == selected else ""}>{e(v)}</option>' for v in values]
    return ''.join(opts)


def setup_card(cfg: dict, project_id: Optional[str], month: Optional[str], action: str = 'start',
               note: str = 'The photos you attached will be analysed.', button: str = 'Start report') -> str:
    projects = ''.join(
        f'<option value="{e(p["id"])}"{" selected" if p["id"] == project_id else ""}>{e(p["name"])}</option>' for p in cfg['projects']
    )
    body = f"""<div class="card"><div class="head"><div><div class="title">Monthly Report</div>
<div class="sub">AI reads each photo; you review and approve. Model {e(cfg.get('model'))} · review threshold {e(cfg.get('confidence_threshold'))}%</div></div></div>
<div class="body" style="display:grid;grid-template-columns:1fr 200px;gap:10px">
<label>Project<select id="project">{projects}</select></label>
<label>Month<input id="month" type="month" value="{e(month or '')}"></label></div>
<div class="actions"><span class="note" id="note">{e(note)}</span><span class="spacer"></span>
<button class="primary" id="go">{e(button)}</button></div></div>"""
    label = '📥 Import Gmail photos for ' if action == 'gmail_import' else '▶️ Start monthly report: '
    script = f"""
const ACTION = {js(action)}, LABEL = {js(label)};
document.getElementById('go').onclick = () => {{
  const project_id = document.getElementById('project').value, month = document.getElementById('month').value;
  if (!month) {{ document.getElementById('month').focus(); return; }}
  send(LABEL + document.getElementById('project').selectedOptions[0].text + ', ' + month, {{ action: ACTION, project_id, month }});
}};"""
    return page(body, script)


def check_line(c: dict) -> str:
    cls, icon = ('ok', '✓') if c['ok'] else ('warn', '⚠')
    detail = ' ({})'.format(c['count']) if c['ok'] else ' missing'
    return '<div class="{}">{} {}{}</div>'.format(cls, icon, c['stage'].title(), detail)


def thumbs_html(ids: list, thumbs: dict) -> str:
    return ''.join('<img src="{}" alt="">'.format(thumbs.get(i, '')) for i in ids)


def coverage_panel(report: dict, thumbs: dict, size: int = 44) -> str:
    out = []
    for g in report['groups']:
        cols = []
        for s in STAGES:
            ids = g['stages'][s]
            imgs = thumbs_html(ids, thumbs) or '<div class="miss">missing</div>'
            cols.append(f'<div><div class="k" style="font-size:11.5px">{s.title()} ({len(ids)})</div><div class="thumbs">{imgs}</div></div>')
        out.append(f'<div class="zone"><b>{e(g["location"])}</b><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px">{"".join(cols)}</div></div>')
    checks = []
    for loc in report['validation']['locations']:
        items = ''.join(check_line(c) for c in loc['checks'])
        checks.append(f'<div class="zone"><b>{e(loc["location"])}</b>{items}</div>')
    extra = ''.join(f'<div class="warn">⚠ {e(m)}</div>' for m in report['validation']['missing'] if ':' not in m)
    return f'<div class="panel">{"".join(out) or "<span class=k>No analysed photos yet.</span>"}</div>', f'<div class="panel"><b>Missing photo check</b>{"".join(checks)}{extra}</div>'


def review_card(report: dict, thumbs: dict) -> str:
    th = report['threshold']
    tiles = []
    for p in report['photos']:
        eff = p['effective']
        flag = p['needs_review']
        reasons = ''.join(f'<div>⚠ {e(r)}</div>' for r in p['review_reasons'])
        err = f'<div class="reasons">{e(p.get("error"))}</div>' if p['status'] == 'error' else ''
        tiles.append(f"""<div class="tile{' flag' if flag else ''}{' excl' if p['excluded'] else ''}" data-id="{e(p['id'])}" data-name="{e(p['filename'])}"
 data-stage="{e(eff.get('stage') or '')}" data-location="{e(eff.get('location') or '')}" data-work="{e(eff.get('work_type') or '')}" data-excluded="{'1' if p['excluded'] else ''}">
<img src="{thumbs.get(p['id'], '')}" alt="{e(p['filename'])}"><div class="in">
<div class="row"><b>{e(p['filename'])}</b>{'<span class="human">Reviewed</span>' if p['reviewed'] else ''}</div>
<div class="row"><span class="k">Type</span>{conf_badge(eff, 'stage', th)}</div>
<select class="f-stage">{options(STAGES, eff.get('stage'))}</select>
<div class="row"><span class="k">Location</span>{conf_badge(eff, 'location', th)}</div>
<select class="f-location">{options(report['project']['zones'], eff.get('location'))}</select>
<div class="row"><span class="k">Work</span>{conf_badge(eff, 'work_type', th)}</div>
<select class="f-work">{options(report['work_types'], eff.get('work_type'))}</select>
<div class="row"><span class="k">Date/time</span><span>{e(eff.get('datetime') or 'Unknown')}</span></div>
<div><span class="k">Issues:</span> {e('; '.join(eff.get('issues') or []) or 'None detected')}</div>
{err}{f'<div class="reasons">{reasons}</div>' if reasons else ''}
<div class="row"><label><input type="checkbox" class="f-checked"{' checked' if p['reviewed'] else ''} style="width:auto"> Checked</label>
<label><input type="checkbox" class="f-excl"{' checked' if p['excluded'] else ''} style="width:auto"> Exclude</label></div>
</div></div>""")
    groups, checks = coverage_panel(report, thumbs)
    flagged = report['needs_review']
    body = f"""<div class="card"><div class="head"><div><div class="title">Photo review · {e(report['project']['name'])}</div>
<div class="sub">{e(month_label(report['month']))} · {e(report['id'])} · {len(report['photos'])} photo(s) · model {e(report['model'])}</div>
<div class="chips"><span class="chip {'warn' if flagged else 'ok'}">{f'⚠ {flagged} need review' if flagged else '✓ No photos need review'}</span>
<span class="chip {'warn' if report['validation']['missing'] else 'ok'}">{f'⚠ {len(report["validation"]["missing"])} missing item(s)' if report['validation']['missing'] else '✓ All Before/During/After present'}</span></div></div></div>
<div class="body"><div class="grid">{''.join(tiles)}</div><div class="two">{groups}{checks}</div></div>
<div class="actions"><span class="note" id="note">Change anything that is wrong, tick Checked on the photos you reviewed.</span><span class="spacer"></span>
<button class="ghost" id="save">Save review</button><button class="primary" id="gen">Save &amp; generate monthly report</button></div></div>"""
    script = f"""
const RID = {js(report['id'])};
document.querySelectorAll('.tile').forEach((t) => t.querySelectorAll('select').forEach((s) => s.addEventListener('change', () => (t.querySelector('.f-checked').checked = true))));
const collect = () => [...document.querySelectorAll('.tile')].map((t) => {{
  const c = {{ photo_id: t.dataset.id, filename: t.dataset.name }};
  const v = (sel) => t.querySelector(sel).value;
  if (v('.f-stage') !== t.dataset.stage) c.stage = v('.f-stage');
  if (v('.f-location') !== t.dataset.location) c.location = v('.f-location');
  if (v('.f-work') !== t.dataset.work) c.work_type = v('.f-work');
  const ex = t.querySelector('.f-excl').checked; if (ex !== !!t.dataset.excluded) c.exclude = ex;
  if (t.querySelector('.f-checked').checked) c.reviewed = true;
  return c;
}}).filter((c) => Object.keys(c).length > 2);
const go = (then) => {{ const changes = collect();
  send((then ? '📝 Save review and generate the monthly report' : '📝 Save photo review') + ' for ' + RID + ' (' + changes.length + ' photo(s) updated)', {{ action: 'update_photos', report: RID, changes, then }}); }};
document.getElementById('save').onclick = () => go(null);
document.getElementById('gen').onclick = () => go('generate');"""
    return page(body, script)


def report_card(report: dict, thumbs: dict, base: str = '/api/v1/bizgpt/monthly-report') -> str:
    content = report.get('content') or {'sections': {}}
    approved = report['status'] == 'approved'
    pdf = f"{base.rstrip('/')}/reports/{report['id']}/pdf"
    editable = report['status'] in ('draft', 'analyzed', 'in_review', 'rejected')
    dis = '' if editable else ' disabled'
    secs = {k: t for k, t in SECTIONS}
    field = lambda k: f'<h4>{e(secs[k])}</h4><textarea data-k="{k}"{dis}>{e(content["sections"].get(k, ""))}</textarea>'  # noqa: E731
    photos = []
    for s in STAGES:
        blocks = ''.join(
            '<div><div class="k" style="font-size:11.5px">{}</div><div class="thumbs">{}</div></div>'.format(
                e(g['location']), thumbs_html(g['stages'][s], thumbs))
            for g in report['groups'] if g['stages'][s]
        ) or '<span class="k">None</span>'
        photos.append(f'<h4>{s.title()} Photos</h4><div style="display:flex;gap:14px;flex-wrap:wrap">{blocks}</div>')
    conf_rows = ''.join(
        f'<tr><td>{e(f["label"])}</td><td class="{"ok" if (f["average_ai_confidence"] or 0) >= report["threshold"] else "warn"}">'
        f'{f["average_ai_confidence"] if f["average_ai_confidence"] is not None else "—"}%</td><td>{f["below_threshold"]}</td><td>{f["unknown"]}</td><td>{f["human_corrected"]}</td></tr>'
        for f in report['confidence']['fields'].values()
    )
    missing = ''.join(f'<div class="warn">⚠ {e(m)}</div>' for m in report['validation']['missing']) or '<div class="ok">✓ None</div>'
    banner = ''
    if report['status'] == 'rejected':
        d = report.get('decision') or {}
        banner = f'<div class="banner bad">Rejected by {e(d.get("by"))}: “{e(d.get("reason"))}”. Edit the text and click Save draft.</div>'
    elif approved:
        d = report.get('decision') or {}
        banner = f'<div class="banner good"><b>✓ Approved</b> by {e(d.get("by"))} on {e(d.get("at"))}. The PDF is ready to view or download.</div>'
    blockers = report['approval_blockers'] if report['status'] == 'in_review' else []
    body = f"""<div class="card"><div class="head"><div><div class="title">MONTHLY MAINTENANCE REPORT</div>
<div class="sub">Project: {e(report['project']['name'])} · Month: {e(month_label(report['month']))} · {e(report['id'])} · {'Approved report' if approved else f'AI draft by {e(content.get("model"))} — human review required'}</div></div></div>
<div class="body">{banner}{field('executive_summary')}{field('location_summary')}{field('work_performed')}{''.join(photos)}
{field('issues_observations')}<h4>Missing Information</h4>{missing}{field('remarks')}
<h4>Coordinator remarks</h4><textarea id="remarks"{dis}>{e(report.get('remarks') or '')}</textarea>
<h4>AI Confidence Summary</h4><table><tr><th>Field</th><th>Avg AI confidence</th><th>Below {report['threshold']}%</th><th>Unknown</th><th>Human corrected</th></tr>{conf_rows}</table>
{f'<div class="reasons" style="margin-top:10px">Before approving: {e("; ".join(blockers))}. You can confirm them when you click Approve.</div>' if blockers else ''}</div>
{approved_bar(pdf, report) if approved else ''}<div class="actions" id="bar"{' style="display:none"' if approved else ''}><span class="note" id="note"></span><span class="spacer"></span>
{'' if approved else fresh_button(report)}<button class="ghost" id="regen">🔁 Regenerate</button><button class="ghost" id="save"{dis}>Save draft</button><button class="reject" id="reject"{'' if report['status'] == 'in_review' else ' disabled'}>Reject</button>
<button class="approve" id="approve"{'' if report['status'] == 'in_review' else ' disabled'}>Approve</button></div>
<div class="actions" id="cf" style="display:none"><span class="note"><b>{report.get('needs_review', 0)} photo(s)</b> are still flagged for review.
Approving confirms the AI values for them.</span><span class="spacer"></span>
<button class="approve" id="cfok">Confirm photos &amp; approve</button><button class="ghost" id="cfno">Cancel</button></div>
<div class="actions" id="rj" style="display:none"><textarea id="reason" placeholder="Reason for rejection"></textarea>
<button class="reject" id="rjok">Confirm reject</button><button class="ghost" id="rjno">Cancel</button></div>{fresh_html(report)}</div>"""
    script = f"""
const RID = {js(report['id'])};
const payload = () => ({{ sections: Object.fromEntries([...document.querySelectorAll('textarea[data-k]')].map((t) => [t.dataset.k, t.value])), remarks: document.getElementById('remarks').value }});
document.getElementById('save').onclick = () => send('💾 Save report draft ' + RID, {{ action: 'save_draft', report: RID, ...payload() }});
document.querySelectorAll('#regen, #again').forEach((b) => (b.onclick = () => send('🔁 Generate the report again for ' + RID, {{ action: 'generate', report: RID }})));
const FLAGGED = {js(report.get('needs_review', 0) if report['status'] == 'in_review' else 0)};
document.getElementById('approve').onclick = () => {{
  if (FLAGGED) {{ document.getElementById('cf').style.display = 'flex'; height(); return; }}
  send('✅ Approve monthly report ' + RID, {{ action: 'approve', report: RID, ...payload() }});
}};
document.getElementById('cfno').onclick = () => {{ document.getElementById('cf').style.display = 'none'; height(); }};
document.getElementById('cfok').onclick = () => send('✅ Confirm the flagged photos and approve monthly report ' + RID,
  {{ action: 'approve', report: RID, confirm_flagged: true, ...payload() }});
document.getElementById('reject').onclick = () => {{ document.getElementById('rj').style.display = 'flex'; document.getElementById('reason').focus(); height(); }};
document.getElementById('rjno').onclick = () => {{ document.getElementById('rj').style.display = 'none'; height(); }};
document.getElementById('rjok').onclick = () => {{ const reason = document.getElementById('reason').value.trim();
  if (reason.length < 3) {{ document.getElementById('reason').focus(); return; }}
  send('❌ Reject monthly report ' + RID + ': ' + reason, {{ action: 'reject', report: RID, reason, ...payload() }}); }};"""
    return page(body, script)


def fresh_html(report: dict) -> str:
    label = month_label(report['month'])
    return f'''<div class="actions" id="freshcf" style="display:none"><span class="note">Delete the <b>{e(label)}</b> report, its photos, PDF
and month folder? The Gmail email can then be imported again from the start.</span><span class="spacer"></span>
<button class="reject" id="freshok">Delete &amp; start fresh</button><button class="ghost" id="freshno">Cancel</button></div>'''


def fresh_button(report: dict) -> str:
    return (f'<button class="ghost" id="fresh" data-rid="{e(report["id"])}" data-label="{e(month_label(report["month"]))}">'
            '🗑 Delete &amp; start fresh</button>')


def approved_bar(pdf: str, report: dict) -> str:
    return f'''<div class="actions"><a class="btn primary" target="_blank" rel="noopener" href="{e(pdf)}">📄 View report</a>
<a class="btn ghost" target="_blank" rel="noopener" href="{e(pdf)}?download=true">⬇️ Download PDF</a>
<button class="ghost" id="again">🔁 Generate again</button>{fresh_button(report)}<span class="note">Same photos always give the same report.</span></div>'''


def approved_card(report: dict, base: str = '/api/v1/bizgpt/monthly-report') -> str:
    d = report.get('decision') or {}
    pdf = f"{base.rstrip('/')}/reports/{report['id']}/pdf"
    body = f"""<div class="card"><div class="body"><div class="banner good" style="font-size:15px;font-weight:700">✓ Report Approved</div>
<table><tr><th>Project</th><td>{e(report['project']['name'])}</td></tr><tr><th>Month</th><td>{e(month_label(report['month']))}</td></tr>
<tr><th>Approved By</th><td>{e(d.get('by'))}</td></tr><tr><th>Approved At</th><td>{e(d.get('at'))}</td></tr><tr><th>Report ID</th><td>{e(report['id'])}</td></tr></table>
</div><div class="actions"><a class="btn primary" target="_blank" rel="noopener" href="{e(pdf)}">📄 View report</a>
<a class="btn ghost" target="_blank" rel="noopener" href="{e(pdf)}?download=true">⬇️ Download PDF</a>
<button class="ghost" id="again">🔁 Generate again</button>{fresh_button(report)}<span class="note" id="note">View, download or generate as often as you like; the same photos always give the same report.</span></div>{fresh_html(report)}</div>"""
    script = f"""document.getElementById('again').onclick = () => send('🔁 Generate the report again for {report['id']}', {{ action: 'generate', report: {js(report['id'])} }});"""
    return page(body, script)
