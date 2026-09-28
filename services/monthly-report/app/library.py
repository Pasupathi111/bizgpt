"""Photo library: every approved report is filed as one folder per project and month.

    library/<project_id>/<YYYY-MM>/
        OCT_0101.jpg ...           the approved photos (excluded ones left out), original file names
        Monthly-Report-<YYYY-MM>.pdf
        photos.json                what each photo shows (stage, location, work) and who approved the report

Re-approving a month replaces its folder, so a folder always holds that month's latest approved report.
"""

import json
import re
import shutil
from pathlib import Path

from . import logic
from .store import Store

MONTH = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
MANIFEST = 'photos.json'


def month_dir(store: Store, project_id: str, month: str) -> Path:
    return store.library_dir / project_id / month


def pdf_name(month: str) -> str:
    return f'Monthly-Report-{month}.pdf'


def file_report(store: Store, report: dict, project: dict) -> Path:
    """Copy the approved photos and the PDF of one report into its month folder."""
    folder = month_dir(store, report['project_id'], report['month'])
    tmp = folder.with_name(folder.name + '.tmp')
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    photos, used = [], set()
    for p in logic.active(store.photos(report['id'])):
        name = _unique(Path(p['filename']).name or f'{p["id"]}.jpg', used)
        shutil.copyfile(p['path'], tmp / name)
        eff = logic.effective(p)
        photos.append({'filename': name, 'stage': eff.get('stage'), 'location': eff.get('location'),
                       'work_type': eff.get('work_type'), 'datetime': eff.get('datetime'), 'issues': eff.get('issues') or []})
    pdf = store.pdf_path(report['id'])
    if pdf.exists():
        shutil.copyfile(pdf, tmp / pdf_name(report['month']))
    decision = report.get('decision') or {}
    (tmp / MANIFEST).write_text(json.dumps({
        'project_id': report['project_id'], 'project_name': project['name'], 'month': report['month'],
        'report_id': report['id'], 'approved_by': decision.get('by'), 'approved_at': decision.get('at'),
        'pdf': pdf.exists(), 'photos': photos,
    }, indent=1))
    shutil.rmtree(folder, ignore_errors=True)
    tmp.rename(folder)
    return folder


def list_months(store: Store) -> list[dict]:
    """All month folders, newest month first."""
    out = []
    for manifest in store.library_dir.glob(f'*/*/{MANIFEST}'):
        data = _read(manifest)
        if data:
            out.append({k: v for k, v in data.items() if k != 'photos'} | {'photo_count': len(data['photos'])})
    return sorted(out, key=lambda m: (m['month'], m['project_name']), reverse=True)


def month_detail(store: Store, project_id: str, month: str) -> dict | None:
    if not MONTH.match(month) or not re.fullmatch(r'[a-z0-9-]+', project_id):
        return None
    return _read(month_dir(store, project_id, month) / MANIFEST)


def file_path(store: Store, project_id: str, month: str, filename: str) -> Path | None:
    """A file inside one month folder; never anything outside it."""
    detail = month_detail(store, project_id, month)
    if not detail or filename != Path(filename).name:
        return None
    allowed = {p['filename'] for p in detail['photos']} | ({pdf_name(month)} if detail.get('pdf') else set())
    path = month_dir(store, project_id, month) / filename
    return path if filename in allowed and path.is_file() else None


def _unique(name: str, used: set) -> str:
    stem, suffix, n = Path(name).stem, Path(name).suffix, 1
    while name.lower() in used:
        n += 1
        name = f'{stem}-{n}{suffix}'
    used.add(name.lower())
    return name


def _read(manifest: Path) -> dict | None:
    try:
        return json.loads(manifest.read_text())
    except (OSError, ValueError):
        return None
