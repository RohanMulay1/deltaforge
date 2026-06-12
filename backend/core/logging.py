"""Logging configuration relocated from ``main.py`` (ARCHITECTURE.md §11.3, §7).

Provides a JSON-ish ``dictConfig`` plus a ``request_id`` context variable that a
middleware/handler can stamp onto every log record (and onto ``ErrorEnvelope``).
The integrator calls ``configure_logging()`` once in the lifespan and installs
``RequestIdMiddleware`` so each request gets a correlatable id.
"""

from __future__ import annotations

import logging
import logging.config
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from core.settings import get_settings

# Per-request correlation id. Defaults to "-" outside a request scope.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdFilter(logging.Filter):
    """Inject the current ``request_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def current_request_id() -> str:
    """Return the request id bound to the current context (or ``"-"``)."""
    return request_id_var.get()


def configure_logging(log_level: str | None = None) -> None:
    """Install the process-wide ``dictConfig`` (idempotent)."""
    level = (log_level or get_settings().log_level).upper()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {"()": "core.logging.RequestIdFilter"},
            },
            "formatters": {
                "json_like": {
                    "format": (
                        '{"time": "%(asctime)s", "level": "%(levelname)s", '
                        '"logger": "%(name)s", "request_id": "%(request_id)s", '
                        '"message": "%(message)s"}'
                    ),
                    "datefmt": "%Y-%m-%dT%H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json_like",
                    "filters": ["request_id"],
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"level": level, "handlers": ["console"]},
        }
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a per-request id and echo it back on the response header."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        incoming = request.headers.get(REQUEST_ID_HEADER)
        rid = incoming or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
