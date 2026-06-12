"""Domain exception taxonomy + error envelope (ARCHITECTURE.md §7).

A single error shape (``ErrorEnvelope``) is returned for every non-2xx
response, matching what the frontend ``AnalyzeForm`` reads (``body.detail``).

Domain exceptions carry their canonical ``error`` code and intended HTTP
``status_code`` so the global handler can map them uniformly. The integrator
(``main.py``) is responsible for registering the actual FastAPI exception
handlers; this module only defines the taxonomy + envelope models.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.schemas_common import PipelineStage

# Canonical error codes (§7). Kept as module constants so handlers and tests
# reference one source of truth rather than scattered string literals.
ERROR_VALIDATION = "validation_error"
ERROR_UPSTREAM_DATA = "upstream_data"
ERROR_WOLFRAM_EVAL = "wolfram_eval"
ERROR_NOT_FOUND = "not_found"
ERROR_RATE_LIMITED = "rate_limited"
ERROR_INTERNAL = "internal"


class FieldError(BaseModel):
    loc: list[str]
    msg: str
    type: str


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    # "validation_error"|"upstream_data"|"wolfram_eval"|"not_found"|"rate_limited"|"internal"
    error: str
    detail: str
    stage: PipelineStage | None = None
    field_errors: list[FieldError] | None = None
    request_id: str
    timestamp: datetime


# ── Domain exception taxonomy (§7) ────────────────────────────────────────────


class DeltaForgeError(Exception):
    """Base class for all DeltaForge domain errors.

    Subclasses set ``error_code`` (a canonical §7 code) and ``status_code``
    (the HTTP status the global handler should emit). ``stage`` optionally
    pins the pipeline stage that raised the error for the ``ErrorEnvelope``.
    """

    error_code: str = ERROR_INTERNAL
    status_code: int = 500

    def __init__(self, detail: str, *, stage: PipelineStage | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.stage = stage


class UpstreamDataError(DeltaForgeError):
    """Upstream market-data provider returned bad/unusable data → 502."""

    error_code = ERROR_UPSTREAM_DATA
    status_code = 502


class SymbolNotFound(DeltaForgeError):
    """Requested symbol does not exist upstream → 404."""

    error_code = ERROR_NOT_FOUND
    status_code = 404


class NoChainData(DeltaForgeError):
    """Symbol exists but has no usable options chain for the filter → 422."""

    error_code = ERROR_VALIDATION
    status_code = 422


class RateLimitError(DeltaForgeError):
    """Caller exceeded the configured rate limit → 429."""

    error_code = ERROR_RATE_LIMITED
    status_code = 429


class NotFoundError(DeltaForgeError):
    """A requested resource (portfolio, analysis, alert) was not found → 404."""

    error_code = ERROR_NOT_FOUND
    status_code = 404


class WolframEvalError(DeltaForgeError):
    """Total compute failure where even the numeric fallback failed → 500.

    Note: a *recoverable* kernel failure must NOT raise — it degrades to
    ``numeric_fallback`` (§7). Only an unrecoverable failure of both paths
    surfaces this error.
    """

    error_code = ERROR_WOLFRAM_EVAL
    status_code = 500
