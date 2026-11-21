"""Configure one-line JSON logging for application and standard-library logs."""
import logging
import re
import sys

import structlog

# These expressions are a best-effort safety net for formatted messages and
# exception text from external libraries. Avoid logging secrets in the first place.
# Match named secrets written as key=value or key: value.
_SECRET = re.compile(
    r"(?i)(\b(?:access_token|refresh_token|api_key|client_secret|password|authorization|cookie|code)\b[\"']?\s*[:=]\s*[\"']?)([^\s&,;\"'}]+)"
)
# Match quoted dictionary-style pairs, including values containing spaces.
_QUOTED_PAIR = re.compile(r"(?i)([\"'](?:access_token|refresh_token|api_key|client_secret|password|authorization|cookie)[\"']\s*:\s*)([\"'])(.*?)\2")
# Remove the entire value of authorization and cookie headers.
_HEADER = re.compile(r"(?im)(\b(?:authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+")
# Catch standalone Basic or Bearer credentials outside a header.
_BEARER = re.compile(r"(?i)(\b(?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+")
# Remove query strings from full HTTP(S) URLs; they can contain secrets.
_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s\"']+")
# Remove credentials embedded before the host in HTTP(S) URLs.
_URL_USERINFO = re.compile(r"(?i)(https?://)[^/@\s]+@")


def _sanitize(value):
    # Inspect nested structured fields as well as already formatted log text.
    if isinstance(value, str):
        value = _URL_USERINFO.sub(r"\1[REDACTED]@", value)
        value = _URL_QUERY.sub(r"\1?[REDACTED]", value)
        value = _QUOTED_PAIR.sub(r"\1\2[REDACTED]\2", value)
        value = _HEADER.sub(r"\1[REDACTED]", value)
        value = _BEARER.sub(r"\1[REDACTED]", value)
        return _SECRET.sub(r"\1[REDACTED]", value)
    if isinstance(value, dict):
        return {key: ('[REDACTED]' if str(key).lower() in {'password', 'token', 'access_token', 'refresh_token', 'api_key', 'client_secret', 'authorization', 'cookie'} else _sanitize(item)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


def _sanitize_event(_logger, _method, event):
    return _sanitize(event)


class _SuppressLoggedRequestErrors(logging.Filter):
    def filter(self, record):
        return not (record.exc_info and getattr(record.exc_info[1], '_albumary_request_logged', False))


def configure_logging() -> None:
    """Install a single JSON handler; safe to call again in either entry point."""
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=shared + [
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _sanitize_event,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared + [structlog.processors.format_exc_info, _sanitize_event],
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, structlog.processors.JSONRenderer()],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    # Replace only handlers installed by this module; preserve test/host handlers.
    for existing in root.handlers[:]:
        if getattr(existing, '_albumary_json', False):
            root.removeHandler(existing)
    handler._albumary_json = True
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ('uvicorn', 'uvicorn.error'):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    uvicorn_error = logging.getLogger('uvicorn.error')
    if not any(isinstance(item, _SuppressLoggedRequestErrors) for item in uvicorn_error.filters):
        uvicorn_error.addFilter(_SuppressLoggedRequestErrors())
    # Default Uvicorn access logs include full query strings. Middleware emits
    # a sanitized request event instead.
    logging.getLogger('uvicorn.access').disabled = True
    logging.getLogger('musicbrainzngs').setLevel(logging.WARNING)
