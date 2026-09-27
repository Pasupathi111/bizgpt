"""Biz GPT Orders: email-driven T-shirt order workflow for the Biz Inbox Orders tab."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .extract import OPENWEBUI_URL, validate
from .gmail import MAILBOX, Gmail
from .store import STATUSES, Store
from .workflow import Workflow, WorkflowError, confirmation_email

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)

store = Store(os.getenv('ORDERS_DB_PATH', '/data/orders.db'))
workflow = Workflow(store, Gmail())
POLLING = os.getenv('ORDERS_POLLING_ENABLED', 'true').lower() == 'true'


@asynccontextmanager
async def lifespan(_app: FastAPI):
    workflow.watermark()
    task = asyncio.create_task(workflow.run_forever()) if POLLING else None
    yield
    if task:
        task.cancel()


app = FastAPI(title='Biz GPT Orders', version='1.0.0', lifespan=lifespan)


# ---------------------------------------------------------------- auth
async def current_user(authorization: str = Header(default='')) -> dict:
    """Any signed-in Biz GPT user (verified with Biz GPT itself)."""
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'Sign in to Biz GPT')
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(f'{OPENWEBUI_URL}/api/v1/auths/', headers={'Authorization': authorization})
        except httpx.HTTPError:
            raise HTTPException(503, 'Biz GPT sign-in check is unavailable')
    user = resp.json() if resp.status_code == 200 else None
    if not user or user.get('role') not in ('user', 'admin'):
        raise HTTPException(401, 'Sign in to Biz GPT')
    return {'id': user.get('id'), 'email': user.get('email'), 'name': user.get('name'), 'role': user['role']}


async def admin_user(user: dict = Depends(current_user)) -> dict:
    if user['role'] != 'admin':
        raise HTTPException(403, 'Only Biz GPT admins can approve or reject orders')
    return user


# ---------------------------------------------------------------- views
def order_view(order: dict, *, with_events: bool = False) -> dict:
    view = {**order, 'validation': validate(order['fields'])}
    view.pop('last_message_id', None)
    if with_events:
        view['events'] = store.events(order['id'])
        if order['status'] == 'ready_for_approval':
            subject, body = confirmation_email(order)
            view['confirmation_preview'] = {'to': order['fields'].get('customer_email'), 'subject': subject, 'body': body}
    return view


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


def _fail(e: WorkflowError):
    raise HTTPException(409, str(e))


# ---------------------------------------------------------------- routes
@app.get('/health')
def health():
    return {'status': 'ok', 'mailbox': MAILBOX, 'polling': POLLING, 'last_poll': workflow.last_poll}


@app.get('/api/status')
def status(user: dict = Depends(current_user)):
    return {
        'mailbox': MAILBOX,
        'polling': POLLING,
        'last_poll': workflow.last_poll,
        'counts': store.counts(),
        'can_decide': user['role'] == 'admin',
    }


@app.get('/api/orders')
def list_orders(status: str | None = Query(default=None), user: dict = Depends(current_user)):
    if status and status not in STATUSES:
        raise HTTPException(400, f'unknown status {status}')
    return {'orders': [order_view(o) for o in store.list_orders(status)], 'counts': store.counts(),
            'can_decide': user['role'] == 'admin'}


@app.get('/api/orders/{order_id}')
def get_order(order_id: str, user: dict = Depends(current_user)):
    order = store.get(order_id)
    if not order:
        raise HTTPException(404, 'Order not found')
    return {**order_view(order, with_events=True), 'can_decide': user['role'] == 'admin'}


@app.post('/api/orders/{order_id}/approve')
async def approve(order_id: str, user: dict = Depends(admin_user)):
    try:
        return order_view(await workflow.approve(order_id, user['email']), with_events=True)
    except WorkflowError as e:
        _fail(e)


@app.post('/api/orders/{order_id}/resend-confirmation')
async def resend_confirmation(order_id: str, user: dict = Depends(admin_user)):
    try:
        return order_view(await workflow.send_confirmation(order_id, user['email']), with_events=True)
    except WorkflowError as e:
        _fail(e)


@app.post('/api/orders/{order_id}/reject')
async def reject(order_id: str, req: RejectRequest, user: dict = Depends(admin_user)):
    try:
        return order_view(await workflow.reject(order_id, user['email'], req.reason), with_events=True)
    except WorkflowError as e:
        _fail(e)


@app.post('/api/poll')
async def poll_now(_user: dict = Depends(admin_user)):
    return await workflow.poll_once()
