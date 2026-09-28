"""Biz GPT Monthly Report POC: photos -> AI analysis -> grouping/validation -> AI report -> human review -> PDF.

AI work lives in ai.py, deterministic business rules in logic.py; this module owns state, files and routes.
"""

import asyncio
import base64
import io
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Cookie, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from . import ai, config, logic
from .gmail import MAILBOX, QUERY, Gmail, GmailError
from .intake import import_from_gmail
from .pdf import build_pdf
from .store import Store

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
log = logging.getLogger('monthly-report')

store = Store(config.DATA_DIR)
gmail = Gmail()
_gmail_state = {'last_check': None, 'last_result': None, 'last_error': None}
_tasks: dict[str, asyncio.Task] = {}
EDITABLE = {'draft', 'analyzed', 'in_review', 'rejected'}
MONTH = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # A restart interrupts processing; leave the report usable (unfinished photos stay pending).
    for r in store.list_reports():
        if r['status'] == 'processing':
            store.update_report(r['id'], status='analyzed', progress={'state': 'interrupted'})
    poller = asyncio.create_task(_poll_gmail()) if config.GMAIL_POLL_SECONDS and config.OPENWEBUI_API_KEY else None
    yield
    if poller:
        poller.cancel()
    for task in _tasks.values():
        task.cancel()


app = FastAPI(title='Biz GPT Monthly Report', version='0.1.0', lifespan=lifespan)


# ---------------------------------------------------------------- auth
async def current_user(authorization: str = Header(default=''), token: str | None = Cookie(default=None)) -> dict:
    """Any signed-in Biz GPT user, verified with Biz GPT itself (header, or the Biz GPT session cookie for links)."""
    if not authorization.lower().startswith('bearer ') and token:
        authorization = f'Bearer {token}'
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'Sign in to Biz GPT')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f'{config.OPENWEBUI_URL}/api/v1/auths/', headers={'Authorization': authorization})
    except httpx.HTTPError:
        raise HTTPException(503, 'Biz GPT sign-in check is unavailable')
    user = resp.json() if resp.status_code == 200 else None
    if not user or user.get('role') not in ('user', 'admin'):
        raise HTTPException(401, 'Sign in to Biz GPT')
    return {'id': user.get('id'), 'email': user.get('email'), 'name': user.get('name') or user.get('email'),
            'role': user['role'], 'token': authorization.split(' ', 1)[1]}


# ---------------------------------------------------------------- helpers
def _report_or_404(rid: str) -> dict:
    report = store.get_report(rid)
    if not report:
        raise HTTPException(404, 'Report not found')
    return report


def _project(report: dict) -> dict:
    project = config.get_project(report['project_id'])
    if not project:
        raise HTTPException(409, f'Project {report["project_id"]} is no longer configured')
    return project


def _require(report: dict, allowed: set[str], action: str):
    if report['status'] not in allowed:
        raise HTTPException(409, f'Cannot {action} while the report is {report["status"].replace("_", " ")}')


def report_view(rid: str) -> dict:
    report = _report_or_404(rid)
    cfg = config.load_config()
    project = _project(report)
    threshold = cfg['confidence_threshold']
    photos = store.photos(rid)
    majority = logic.work_type_majority(photos)
    views = [logic.photo_view(p, threshold, majority) for p in photos]
    validation = logic.validate(photos, project['zones'], cfg['required_stages'])
    return {
        **report,
        'project': project,
        'threshold': threshold,
        'model': config.MODEL,
        'stages': ai.STAGES,
        'work_types': cfg['work_types'],
        'photos': views,
        'groups': logic.group(photos, project['zones']),
        'validation': validation,
        'confidence': logic.confidence_summary(photos, threshold),
        'needs_review': sum(1 for v in views if v['needs_review']),
        'approval_blockers': logic.approval_blockers(report, views),
        'events': store.events(rid),
        'has_pdf': report['status'] == 'approved' and store.pdf_path(rid).exists(),
    }


def _exif_datetime(img: Image.Image) -> str | None:
    try:
        exif = img.getexif()
        raw = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)  # DateTimeOriginal, DateTime
        if raw:
            return datetime.strptime(str(raw).strip(), '%Y:%m:%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
    except (ValueError, KeyError, AttributeError):
        pass
    return None


def _store_image(rid: str, name: str, data: bytes) -> str | None:
    """Validate and store one photo; returns the reason when it is rejected."""
    if len(data) > config.MAX_PHOTO_BYTES:
        return 'file is too large'
    if len(store.photos(rid)) >= config.MAX_PHOTOS:
        return f'the report already holds {config.MAX_PHOTOS} photos'
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or '').upper()
            exif_dt = _exif_datetime(img)
    except (UnidentifiedImageError, OSError, SyntaxError):
        return 'not a readable image'
    if fmt not in ('JPEG', 'PNG', 'WEBP', 'MPO'):
        return f'{fmt or "this"} format is not supported (use JPG, PNG or WEBP)'
    store.add_photo(rid, name.replace('/', '_')[-120:], data, f'image/{fmt.lower()}', exif_dt)
    return None


def _start_processing(rid: str, auth: str, actor: str | None) -> bool:
    """Analyse the report's new photos in the background (no-op when nothing is pending or it already runs)."""
    if rid in _tasks:
        return False
    targets = [p['id'] for p in store.photos(rid) if p['status'] in ('pending', 'error')]
    if not targets:
        return False
    store.update_report(rid, status='processing', progress={'state': 'running', 'total': len(targets), 'done': 0, 'failed': 0})
    store.event(rid, 'processing_started', actor, f'{len(targets)} photo(s) with {config.MODEL}')
    _tasks[rid] = asyncio.create_task(_process(rid, auth, targets))
    return True


# ---------------------------------------------------------------- AI processing (background)
async def _process(rid: str, auth: str, photo_ids: list[str]):
    cfg = config.load_config()
    report = store.get_report(rid)
    project = config.get_project(report['project_id'])
    done = failed = 0
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        for pid in photo_ids:
            store.update_report(rid, progress={'state': 'running', 'total': len(photo_ids), 'done': done, 'failed': failed,
                                               'current': pid, 'started_at': started})
            photo = store.get_photo(rid, pid)
            if not photo:
                continue
            store.update_photo(pid, status='analyzing', error=None)
            try:
                result = await ai.analyse_photo(photo['path'], project, cfg['work_types'], auth)
                store.update_photo(pid, status='analyzed', ai=result, error=None, reviewed=0)
                done += 1
            except ai.ModelError as e:
                store.update_photo(pid, status='error', error=str(e))
                failed += 1
                log.warning('photo %s failed: %s', pid, e)
            except Exception as e:  # noqa: BLE001 - one bad photo must not stop the batch
                store.update_photo(pid, status='error', error=f'analysis failed ({type(e).__name__})')
                failed += 1
                log.exception('photo %s crashed', pid)
        store.update_report(rid, status='analyzed', progress={'state': 'finished', 'total': len(photo_ids), 'done': done,
                                                              'failed': failed, 'started_at': started})
        store.event(rid, 'analyzed', None, f'{done} analysed, {failed} failed')
    except asyncio.CancelledError:
        store.update_report(rid, status='analyzed', progress={'state': 'interrupted'})
        raise
    finally:
        _tasks.pop(rid, None)


# ---------------------------------------------------------------- models
class CreateReport(BaseModel):
    project_id: str
    month: str


class PhotoUpdate(BaseModel):
    stage: str | None = Field(default=None)
    location: str | None = None
    work_type: str | None = None
    issues: list[str] | None = None
    datetime: str | None = Field(default=None, max_length=40)
    excluded: bool | None = None
    reviewed: bool | None = None
    fields_set: list[str] = Field(default_factory=list, description='Which of stage/location/work_type/issues/datetime to change')


class DraftUpdate(BaseModel):
    sections: dict[str, str] | None = None
    remarks: str | None = Field(default=None, max_length=4000)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class IntakeRequest(BaseModel):
    reference: str
    values: dict
    context: dict = Field(default_factory=dict)


# ---------------------------------------------------------------- routes
@app.get('/health')
def health():
    return {'status': 'ok', 'model': config.MODEL}


@app.get('/api/config')
def get_config(_user: dict = Depends(current_user)):
    cfg = config.load_config()
    return {**cfg, 'model': config.MODEL, 'max_photos': config.MAX_PHOTOS}


@app.get('/api/reports')
def list_reports(_user: dict = Depends(current_user)):
    projects = {p['id']: p['name'] for p in config.load_config()['projects']}
    return {'reports': [{**r, 'project_name': projects.get(r['project_id'], r['project_id'])} for r in store.list_reports()]}


@app.post('/api/reports')
def create_report(req: CreateReport, user: dict = Depends(current_user)):
    if not config.get_project(req.project_id):
        raise HTTPException(400, 'Unknown project')
    if not MONTH.match(req.month):
        raise HTTPException(400, 'Month must be YYYY-MM')
    return report_view(store.create_report(req.project_id, req.month, user['email'])['id'])


@app.post('/api/intake')
def intake(req: IntakeRequest):
    """Webhook from the Biz GPT Dynamic Forms service (form type monthly_report_request)."""
    projects = config.load_config()['projects']
    wanted = str(req.values.get('project') or '').strip().lower()
    project = next((p for p in projects if wanted in (p['id'].lower(), p['name'].lower())), None)
    month = str(req.values.get('month') or '')
    if not project:
        raise HTTPException(400, 'Unknown project')
    if not MONTH.match(month):
        raise HTTPException(400, 'Month must be YYYY-MM')
    rid = re.sub(r'[^A-Z0-9-]', '', req.reference.upper())[:20] or None
    if rid and store.get_report(rid):
        raise HTTPException(409, 'Report already exists')
    report = store.create_report(project['id'], month, req.context.get('user_email'), report_id=rid)
    if req.values.get('remarks'):
        store.update_report(report['id'], remarks=str(req.values['remarks'])[:4000])
    return {'report_id': report['id'], 'path': f'/monthly-report?report={report["id"]}'}


@app.get('/api/reports/{rid}')
def get_report(rid: str, _user: dict = Depends(current_user)):
    return report_view(rid)


@app.post('/api/reports/{rid}/photos')
async def upload_photos(rid: str, files: list[UploadFile] = File(...), user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    _require(report, EDITABLE, 'add photos')
    existing = len(store.photos(rid))
    if existing + len(files) > config.MAX_PHOTOS:
        raise HTTPException(400, f'A report can hold at most {config.MAX_PHOTOS} photos')
    added, rejected = [], []
    for f in files:
        data = await f.read()
        name = (f.filename or 'photo.jpg').replace('/', '_')[-120:]
        problem = _store_image(rid, name, data)
        if problem:
            rejected.append({'filename': name, 'reason': problem})
        else:
            added.append(name)
    if added:
        store.event(rid, 'photos_uploaded', user['email'], f'{len(added)} photo(s)')
    return {'added': len(added), 'rejected': rejected, 'report': report_view(rid)}


@app.delete('/api/reports/{rid}/photos/{pid}')
def delete_photo(rid: str, pid: str, user: dict = Depends(current_user)):
    _require(_report_or_404(rid), EDITABLE, 'remove photos')
    if not store.delete_photo(rid, pid):
        raise HTTPException(404, 'Photo not found')
    store.event(rid, 'photo_removed', user['email'], pid)
    return report_view(rid)


@app.get('/api/reports/{rid}/photos/{pid}/image')
def photo_image(rid: str, pid: str, size: int = Query(default=480, ge=64, le=2048), _user: dict = Depends(current_user)):
    photo = store.get_photo(rid, pid)
    if not photo:
        raise HTTPException(404, 'Photo not found')
    with Image.open(photo['path']) as img:
        img = ImageOps.exif_transpose(img).convert('RGB')
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=82)
    return Response(buf.getvalue(), media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=300'})


@app.post('/api/reports/{rid}/process')
async def process(rid: str, all: bool = Query(default=False), user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    _require(report, EDITABLE, 'process photos')
    photos = store.photos(rid)
    targets = [p['id'] for p in photos if all or p['status'] in ('pending', 'error', 'analyzing')]
    if not photos:
        raise HTTPException(400, 'Upload photos first')
    if not targets:
        raise HTTPException(400, 'All photos are already analysed')
    store.update_report(rid, status='processing', progress={'state': 'running', 'total': len(targets), 'done': 0, 'failed': 0})
    store.event(rid, 'processing_started', user['email'], f'{len(targets)} photo(s) with {config.MODEL}')
    _tasks[rid] = asyncio.create_task(_process(rid, user['token'], targets))
    return report_view(rid)


@app.patch('/api/reports/{rid}/photos/{pid}')
def update_photo(rid: str, pid: str, req: PhotoUpdate, user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    _require(report, EDITABLE, 'edit photos')
    photo = store.get_photo(rid, pid)
    if not photo:
        raise HTTPException(404, 'Photo not found')
    project = _project(report)
    cfg = config.load_config()
    overrides = dict(photo['overrides'])
    allowed = {'stage': ai.STAGES, 'location': project['zones'], 'work_type': cfg['work_types']}
    for field in req.fields_set:
        if field not in ('stage', 'location', 'work_type', 'issues', 'datetime'):
            raise HTTPException(400, f'Cannot change {field}')
        value = getattr(req, field)
        if field in allowed and value is not None and value not in allowed[field]:
            raise HTTPException(400, f'{value!r} is not an allowed {field.replace("_", " ")}')
        if field == 'issues':
            value = [str(i).strip()[:200] for i in (value or []) if str(i).strip()][:10]
        overrides[field] = value
    changes = {'overrides': overrides}
    if req.excluded is not None:
        changes['excluded'] = int(req.excluded)
    if req.reviewed is not None:
        changes['reviewed'] = int(req.reviewed)
    elif req.fields_set:
        changes['reviewed'] = 1  # a human correction is a review
    store.update_photo(pid, **changes)
    store.event(rid, 'photo_reviewed', user['email'], f'{photo["filename"]}: {", ".join(req.fields_set) or "confirmed"}'
                + (' (excluded)' if req.excluded else ''))
    return report_view(rid)


@app.post('/api/reports/{rid}/generate')
async def generate(rid: str, user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    _require(report, EDITABLE, 'generate the report')
    project = _project(report)
    cfg = config.load_config()
    photos = store.photos(rid)
    if not logic.active(photos):
        raise HTTPException(400, 'Process photos first: no analysed photos yet')
    validation = logic.validate(photos, project['zones'], cfg['required_stages'])
    try:
        sections = await ai.write_report(logic.facts(report, project, photos, validation), user['token'])
    except ai.ModelError as e:
        raise HTTPException(502, f'Report generation failed: {e}')
    content = {'sections': sections, 'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'model': config.MODEL, 'ai_sections': dict(sections)}
    store.update_report(rid, content=content, status='in_review', decision=None)
    store.event(rid, 'report_generated', user['email'], config.MODEL)
    return report_view(rid)


@app.put('/api/reports/{rid}/draft')
def save_draft(rid: str, req: DraftUpdate, user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    _require(report, EDITABLE, 'save the draft')
    changes = {}
    if req.sections is not None:
        if not report['content']:
            raise HTTPException(400, 'Generate the report first')
        content = report['content']
        content['sections'] = {k: str(req.sections.get(k, content['sections'].get(k, '')))[:6000] for k in ai.NARRATIVE_KEYS}
        content['edited_by'] = user['email']
        changes['content'] = content
    if req.remarks is not None:
        changes['remarks'] = req.remarks
    if report['status'] == 'rejected' and report['content']:
        changes['status'] = 'in_review'
    store.update_report(rid, **changes)
    store.event(rid, 'draft_saved', user['email'])
    return report_view(rid)


@app.post('/api/reports/{rid}/reject')
def reject(rid: str, req: RejectRequest, user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    _require(report, {'in_review'}, 'reject')
    store.update_report(rid, status='rejected', decision={'status': 'rejected', 'by': user['name'], 'by_email': user['email'],
                                                          'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                                          'reason': req.reason})
    store.event(rid, 'rejected', user['email'], req.reason)
    return report_view(rid)


@app.post('/api/reports/{rid}/approve')
def approve(rid: str, user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    _require(report, {'in_review'}, 'approve')
    view = report_view(rid)
    if view['approval_blockers']:
        raise HTTPException(409, 'Cannot approve yet: ' + '; '.join(view['approval_blockers']))
    decision = {'status': 'approved', 'by': user['name'], 'by_email': user['email'],
                'at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    report['decision'] = decision
    project = _project(report)
    photos = store.photos(rid)
    try:
        build_pdf(store.pdf_path(rid), report, project, photos, view['validation'], view['confidence'])
    except Exception as e:  # noqa: BLE001
        log.exception('pdf failed for %s', rid)
        raise HTTPException(500, f'PDF generation failed ({type(e).__name__}); the report was not approved')
    store.update_report(rid, status='approved', decision=decision)
    store.event(rid, 'approved', user['email'], 'PDF generated')
    return report_view(rid)


@app.get('/api/reports/{rid}/pdf')
def get_pdf(rid: str, download: bool = False, _user: dict = Depends(current_user)):
    report = _report_or_404(rid)
    path = store.pdf_path(rid)
    if report['status'] != 'approved' or not path.exists():
        raise HTTPException(404, 'The PDF is available after approval')
    return FileResponse(path, media_type='application/pdf', filename=f'Monthly-Report-{rid}.pdf',
                        content_disposition_type='attachment' if download else 'inline')


@app.get('/api/reports/{rid}/thumbs')
def photo_thumbs(rid: str, size: int = Query(default=128, ge=48, le=512), _user: dict = Depends(current_user)):
    """Small inline thumbnails (data URLs) for chat cards, which cannot send auth headers."""
    _report_or_404(rid)
    out = {}
    for p in store.photos(rid):
        try:
            with Image.open(p['path']) as img:
                img = ImageOps.exif_transpose(img).convert('RGB')
                img.thumbnail((size, size))
                buf = io.BytesIO()
                img.save(buf, 'JPEG', quality=70)
            out[p['id']] = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
        except (OSError, UnidentifiedImageError):
            continue
    return out


class InterpretRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    report_id: str | None = None


@app.post('/api/interpret')
async def interpret(req: InterpretRequest, user: dict = Depends(current_user)):
    """Chat: turn a coordinator's free-text message into one validated action (AI reads, application validates)."""
    cfg = config.load_config()
    report = store.get_report(req.report_id) if req.report_id else None
    photos = store.photos(report['id']) if report else []
    zones = (config.get_project(report['project_id']) or {}).get('zones', []) if report else []
    try:
        raw = ai.parse_json(await ai.complete(
            [{'role': 'user', 'content': ai.interpret_prompt(req.text, cfg, report, [p['filename'] for p in photos], zones)}],
            user['token']))
    except ai.ModelError as e:
        raise HTTPException(502, f'Could not understand the message: {e}')
    return ai.normalise_intent(raw, cfg, photos, zones, req.text)


# ---------------------------------------------------------------- Gmail intake
async def _run_gmail_import(auth: str, actor: str | None, project_id: str | None = None, month: str | None = None) -> dict:
    if project_id and not config.get_project(project_id):
        raise HTTPException(400, 'Unknown project')
    if month and not MONTH.match(month):
        raise HTTPException(400, 'Month must be YYYY-MM')
    _gmail_state['last_check'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    try:
        result = await import_from_gmail(store, gmail, lambda rid, name, data: _store_image(rid, name, data) is None,
                                         auth, project_id=project_id, month=month, created_by=actor)
    except GmailError as e:
        _gmail_state['last_error'] = str(e)
        raise HTTPException(502, str(e))
    _gmail_state.update(last_result={k: len(v) for k, v in result.items()}, last_error=None)
    for rid in result['reports']:
        _start_processing(rid, auth, actor or 'gmail')
    return result


async def _poll_gmail():
    """Optional: check the mailbox on a timer (needs MONTHLY_REPORT_OPENWEBUI_API_KEY for the model calls)."""
    while True:
        try:
            await _run_gmail_import(config.OPENWEBUI_API_KEY, 'gmail')
        except HTTPException as e:
            log.warning('gmail poll failed: %s', e.detail)
        except Exception:  # noqa: BLE001 - keep polling
            log.exception('gmail poll crashed')
        await asyncio.sleep(config.GMAIL_POLL_SECONDS)


class GmailImportRequest(BaseModel):
    project_id: str | None = None
    month: str | None = None


@app.post('/api/gmail/import')
async def gmail_import(req: GmailImportRequest, user: dict = Depends(current_user)):
    """Fetch new site-photo emails now; their photos join the matching report and are analysed."""
    result = await _run_gmail_import(user['token'], user['email'], req.project_id, req.month)
    return {**result, 'mailbox': MAILBOX}


@app.get('/api/gmail/status')
def gmail_status(_user: dict = Depends(current_user)):
    return {'mailbox': MAILBOX, 'query': QUERY, 'auto_check_seconds': config.GMAIL_POLL_SECONDS if config.OPENWEBUI_API_KEY else 0,
            **_gmail_state, 'recent': store.gmail_recent(20)}
