"""Deterministic business logic: effective values, review flags, grouping, missing photos, summaries.

No model calls here. The same inputs always give the same answer.
"""

from .ai import STAGES

UNASSIGNED = 'Unassigned'
FIELDS = ('stage', 'location', 'work_type')


def effective(photo: dict) -> dict:
    """AI values with the coordinator's corrections applied on top. Human values count as 100%."""
    ai = photo.get('ai') or {}
    ov = photo.get('overrides') or {}
    out = {}
    for field in FIELDS:
        if field in ov:
            out[field] = ov[field] or None
            out[f'{field}_confidence'] = 100 if ov[field] else 0
            out[f'{field}_source'] = 'human'
        else:
            out[field] = ai.get(field)
            out[f'{field}_confidence'] = ai.get(f'{field}_confidence', 0) if ai.get(field) else 0
            out[f'{field}_source'] = 'ai'
    out['issues'] = ov['issues'] if 'issues' in ov else ai.get('issues', [])
    out['description'] = ai.get('description', '')
    out['datetime'] = ov.get('datetime') or photo.get('exif_datetime') or ai.get('datetime_text')
    return out


def work_type_majority(photos: list[dict]) -> dict[str, str]:
    """{location: work type} where at least two photos of that location agree and they are the majority."""
    by_zone: dict[str, list[str]] = {}
    for p in active(photos):
        eff = effective(p)
        if eff['location'] and eff['work_type']:
            by_zone.setdefault(eff['location'], []).append(eff['work_type'])
    out = {}
    for zone, types in by_zone.items():
        top = max(set(types), key=types.count)
        if types.count(top) >= 2 and types.count(top) * 2 > len(types):
            out[zone] = top
    return out


def review_reasons(photo: dict, threshold: int, majority: dict[str, str] | None = None) -> list[str]:
    """Why a photo still needs a human look. Empty when it is fine or a human confirmed it."""
    if photo.get('excluded') or photo.get('reviewed'):
        return []
    if photo['status'] == 'error':
        return [f'AI analysis failed: {photo.get("error") or "unknown error"}']
    if photo['status'] != 'analyzed':
        return []
    eff = effective(photo)
    reasons = []
    labels = {'stage': 'Classification', 'location': 'Location', 'work_type': 'Work type'}
    for field in FIELDS:
        if not eff[field]:
            reasons.append(f'{labels[field]} unknown')
        elif eff[f'{field}_confidence'] < threshold:
            reasons.append(f'{labels[field]} confidence {eff[f"{field}_confidence"]}% is below {threshold}%')
    conflicts = (photo.get('ai') or {}).get('stage_conflicts') or []
    if conflicts and eff['stage_source'] == 'ai':
        reasons.append(f'Classification {eff["stage"]} conflicts with the photo: {"; ".join(conflicts)}')
    expected = (majority or {}).get(eff['location'] or '')
    if expected and eff['work_type'] and eff['work_type'] != expected and eff['work_type_source'] == 'ai':
        reasons.append(f'Work type {eff["work_type"]} differs from the other {eff["location"]} photos ({expected})')
    return reasons


def photo_view(photo: dict, threshold: int, majority: dict[str, str] | None = None) -> dict:
    view = {k: v for k, v in photo.items() if k != 'path'}
    view['effective'] = effective(photo)
    view['review_reasons'] = review_reasons(photo, threshold, majority)
    view['needs_review'] = bool(view['review_reasons'])
    return view


def active(photos: list[dict]) -> list[dict]:
    return [p for p in photos if not p.get('excluded') and p['status'] == 'analyzed']


def group(photos: list[dict], zones: list[str]) -> list[dict]:
    """[{location, stages: {BEFORE: [photo ids], DURING, AFTER, UNKNOWN}}] in project zone order."""
    groups: dict[str, dict] = {}
    for p in active(photos):
        eff = effective(p)
        loc = eff['location'] or UNASSIGNED
        stage = eff['stage'] or 'UNKNOWN'
        g = groups.setdefault(loc, {s: [] for s in [*STAGES, 'UNKNOWN']})
        g[stage].append(p['id'])
    order = [z for z in zones if z in groups] + [z for z in groups if z not in zones]
    return [{'location': loc, 'stages': groups[loc]} for loc in order]


def validate(photos: list[dict], zones: list[str], required_stages: list[str]) -> dict:
    """Missing-photo checks per project zone, plus photos that could not be placed."""
    groups = {g['location']: g['stages'] for g in group(photos, zones)}
    locations, missing = [], []
    for zone in zones:
        stages = groups.get(zone)
        if not stages:
            locations.append({'location': zone, 'has_photos': False, 'checks': [{'stage': s, 'ok': False, 'count': 0} for s in required_stages]})
            missing.append(f'{zone}: no photos uploaded')
            continue
        checks = [{'stage': s, 'ok': bool(stages[s]), 'count': len(stages[s])} for s in required_stages]
        locations.append({'location': zone, 'has_photos': True, 'checks': checks})
        missing += [f'{zone}: {c["stage"].title()} photo missing' for c in checks if not c['ok']]
    unassigned = sum(len(v) for v in groups.get(UNASSIGNED, {}).values())
    unclassified = sum(len(g.get('UNKNOWN', [])) for g in groups.values())
    if unassigned:
        missing.append(f'{unassigned} photo(s) have no location')
    if unclassified:
        missing.append(f'{unclassified} photo(s) are not classified as Before/During/After')
    return {'locations': locations, 'missing': missing, 'complete': not missing}


def confidence_summary(photos: list[dict], threshold: int) -> dict:
    rows = active(photos)
    summary = {'threshold': threshold, 'photos_analyzed': len(rows), 'fields': {}}
    for field, label in (('stage', 'Classification'), ('location', 'Location'), ('work_type', 'Work type')):
        values = [effective(p) for p in rows]
        ai_values = [v[f'{field}_confidence'] for v in values if v[f'{field}_source'] == 'ai' and v[field]]
        summary['fields'][field] = {
            'label': label,
            'average_ai_confidence': round(sum(ai_values) / len(ai_values)) if ai_values else None,
            'below_threshold': sum(1 for c in ai_values if c < threshold),
            'unknown': sum(1 for v in values if not v[field]),
            'human_corrected': sum(1 for v in values if v[f'{field}_source'] == 'human'),
        }
    summary['human_reviewed_photos'] = sum(1 for p in rows if p.get('reviewed'))
    return summary


def facts(report: dict, project: dict, photos: list[dict], validation: dict) -> dict:
    """The only information the model may use when writing the report narrative."""
    by_id = {p['id']: effective(p) for p in active(photos)}
    locations = []
    for g in group(photos, project['zones']):
        ids = [i for ids in g['stages'].values() for i in ids]
        locations.append({
            'location': g['location'],
            'photo_counts': {s.title(): len(v) for s, v in g['stages'].items() if v},
            'work_types': sorted({by_id[i]['work_type'] for i in ids if by_id[i]['work_type']}),
            'issues': sorted({issue for i in ids for issue in by_id[i]['issues']}),
            'photo_notes': [by_id[i]['description'] for i in ids if by_id[i]['description']][:6],
        })
    return {
        'project': project['name'],
        'client': project.get('client'),
        'month': report['month'],
        'total_photos': len(by_id),
        'locations': locations,
        'missing_information': validation['missing'],
        'coordinator_remarks': report.get('remarks') or '',
    }


def approval_blockers(report: dict, photo_views: list[dict]) -> list[str]:
    blockers = []
    if not report.get('content'):
        blockers.append('Generate the report first')
    pending = [p for p in photo_views if p['needs_review']]
    if pending:
        blockers.append(f'{len(pending)} photo(s) still need human review')
    return blockers
