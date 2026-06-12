"""CORS configuration from an env allowlist (ARCHITECTURE.md §11.3).

The legacy ``allow_origins=["*"]`` combined with ``allow_credentials=True`` is
invalid/unsafe. This module derives the explicit allowlist from
``CORS_ALLOW_ORIGINS`` and configures the FastAPI middleware accordingly. The
integrator wires ``configure_cors(app)`` in ``main.py``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Localhost fallback used only when the allowlist resolves empty, so that local
# development never silently breaks. Production must set CORS_ALLOW_ORIGINS.
_LOCAL_FALLBACK_ORIGINS: tuple[str, ...] = ("http://localhost:3000",)


def resolve_cors_origins(settings: Settings | None = None) -> list[str]:
    """Return the explicit CORS allowlist (never ``["*"]``)."""
    settings = settings or get_settings()
    origins = settings.cors_origins_list()
    if not origins:
        logger.warning(
            "CORS allowlist empty; using localhost fallback",
            extra={"fallback": list(_LOCAL_FALLBACK_ORIGINS)},
        )
        return list(_LOCAL_FALLBACK_ORIGINS)
    return origins


def configure_cors(app: FastAPI, settings: Settings | None = None) -> None:
    """Attach the CORS middleware using the env-derived allowlist."""
    origins = resolve_cors_origins(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    logger.info("CORS configured", extra={"allow_origins": origins})
