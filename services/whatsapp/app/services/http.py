"""Retry helper shared by the Meta and Open WebUI clients."""

import asyncio
import logging

import httpx

from app.logging_setup import log_extra

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 0.5,
    service: str = 'http',
    idempotent: bool = True,
    **kwargs,
) -> httpx.Response:
    """Retry timeouts, connection errors, 429 and 5xx with exponential backoff. 4xx is returned at once.

    idempotent=False (sending a message) only retries failures where the request surely never
    reached the server (connect errors, 429), so a customer never gets the same reply twice.
    """
    attempts = max(1, retries)
    retry_statuses = RETRY_STATUSES if idempotent else {429}
    for attempt in range(1, attempts + 1):
        try:
            response = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            safe = idempotent or isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
            if attempt == attempts or not safe:
                raise
            log.warning('request failed, retrying', **log_extra(service=service, attempt=attempt, error=type(exc).__name__))
        else:
            if response.status_code not in retry_statuses or attempt == attempts:
                return response
            log.warning('request failed, retrying', **log_extra(service=service, attempt=attempt, status=response.status_code))
            retry_after = response.headers.get('retry-after')
            if retry_after and retry_after.isdigit():
                await asyncio.sleep(min(float(retry_after), 10.0))
                continue
        await asyncio.sleep(backoff * (2 ** (attempt - 1)))
    raise RuntimeError('unreachable')  # pragma: no cover
