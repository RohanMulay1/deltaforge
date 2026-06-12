"""Rate limiting via slowapi (ARCHITECTURE.md §11.3).

``/analyze`` is tighter; SSE (``/analyze/stream``) is looser. The limiter is
constructed from env-configured limits in ``core/settings.py``. The integrator
attaches the limiter + exception handler in ``main.py``; routers reference the
shared ``limiter`` and decorate routes with per-route limits.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from slowapi import Limiter
from slowapi.util import get_remote_address

from core.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_limiter() -> Limiter:
    """Return a process-wide cached slowapi ``Limiter``.

    Keyed by remote address. The default limit applies to any route without an
    explicit ``@limiter.limit(...)`` decorator. When ``RATE_LIMIT_ENABLED`` is
    False, limiting is disabled (useful for tests/local).
    """
    settings: Settings = get_settings()
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_default],
        enabled=settings.rate_limit_enabled,
    )
    logger.info(
        "Rate limiter configured",
        extra={
            "default": settings.rate_limit_default,
            "analyze": settings.rate_limit_analyze,
            "stream": settings.rate_limit_stream,
            "enabled": settings.rate_limit_enabled,
        },
    )
    return limiter


def analyze_limit() -> str:
    """Return the per-route limit string for the tight ``/analyze`` endpoints."""
    return get_settings().rate_limit_analyze


def stream_limit() -> str:
    """Return the per-route limit string for the looser SSE stream endpoint."""
    return get_settings().rate_limit_stream
