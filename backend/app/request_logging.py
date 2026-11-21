"""Request correlation and access events without raw paths or query strings."""
import time
import uuid

import structlog
from structlog.contextvars import bound_contextvars

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status_code = 500

        async def send_response(message):
            nonlocal status_code
            if message['type'] == 'http.response.start':
                status_code = message['status']
            await send(message)

        with bound_contextvars(request_id=uuid.uuid4().hex):
            try:
                await self.app(scope, receive, send_response)
            except Exception as exc:
                logger.exception('http_request_failed')
                # Uvicorn also logs the same exception after the request
                # context is gone. Its filter suppresses only this duplicate.
                try:
                    setattr(exc, '_albumary_request_logged', True)
                except (AttributeError, TypeError):
                    pass
                raise
            finally:
                logger.info('http_request_completed', method=scope['method'], route=getattr(scope.get('route'), 'path', '<unmatched>'), status_code=status_code,
                            duration_ms=round((time.perf_counter() - started) * 1000, 3))
