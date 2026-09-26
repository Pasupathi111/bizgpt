"""Biz GPT WhatsApp integration service.

A separate backend between the Meta WhatsApp Cloud API and Biz GPT (Open WebUI):

    customer -> Meta -> POST /api/whatsapp/webhook -> store -> Biz GPT agent -> Meta -> customer

It talks to Biz GPT only through its HTTP API and holds the WhatsApp credentials itself.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api import conversations, health, webhook, whatsapp
from app.config import Settings, get_settings
from app.db import create_all, get_engine, init_engine, session_factory
from app.logging_setup import log_extra, setup_logging
from app.services.meta_api_service import MetaAPIService
from app.services.openwebui_service import OpenWebUIService
from app.services.whatsapp_service import WhatsAppService

log = logging.getLogger('whatsapp')


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None, create_tables: bool = False) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.log_level, settings.secret_values())
        init_engine(settings.database_url)
        if create_tables:
            await create_all()
        client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        app.state.settings = settings
        app.state.meta = MetaAPIService(settings, client, backoff=0.0 if transport else 0.5)
        app.state.openwebui = OpenWebUIService(settings, client, backoff=0.0 if transport else 0.5)
        app.state.whatsapp = WhatsAppService(settings, session_factory(), app.state.meta, app.state.openwebui)
        if not settings.whatsapp_app_secret.get_secret_value():
            log.warning('WHATSAPP_APP_SECRET not set: webhook signatures are NOT verified')
        if not settings.whatsapp_service_api_key.get_secret_value():
            log.warning('WHATSAPP_SERVICE_API_KEY not set: internal API is disabled')
        log.info('whatsapp service started', **log_extra(meta_configured=settings.meta_configured, agent=settings.whatsapp_agent_model))
        resume = None if create_tables else asyncio.create_task(app.state.whatsapp.resume_pending())
        try:
            yield
        finally:
            if resume and not resume.done():
                resume.cancel()
            await client.aclose()
            await get_engine().dispose()

    app = FastAPI(title='Biz GPT WhatsApp Integration', version='1.0.0', lifespan=lifespan, docs_url='/docs', redoc_url=None)
    app.include_router(health.router)
    app.include_router(webhook.router)
    app.include_router(whatsapp.router)
    app.include_router(conversations.router)
    return app


app = create_app(create_tables=get_settings().database_url.startswith('sqlite'))
