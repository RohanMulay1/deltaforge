"""DeltaForge FastAPI application factory (ARCHITECTURE.md §2, §7, §11).

Thin composition root. It owns NO business logic — it only:

  * loads ``core.settings`` (fail-fast on missing secrets) + configures logging,
  * creates the shared ``ThreadPoolExecutor`` used by both yfinance (off-loop
    blocking calls) and the local Wolfram kernel pool,
  * constructs ``WolframService`` and runs a startup health probe (expecting
    ``engine_in_use="wolfram"`` when the local Engine 14.3 kernel is present;
    degrading gracefully to ``numeric_fallback`` otherwise),
  * builds the market-data provider via the WS1 factory,
  * creates the async DB engine / session factory,
  * wires CORS (env allowlist), the slowapi limiter, and the ``ErrorEnvelope``
    exception handlers mapping the ``backend/errors.py`` taxonomy,
  * mounts the real ``/health`` and ``/health/wolfram`` endpoints,
  * includes the routers that exist today (portfolios, watchlist, history).

The analyze / scenario / alerts routers belong to WS2 / WS4 and are mounted via
the clearly-marked placeholder block below once those workstreams land.

Shared singletons constructed in the lifespan are stored on ``app.state`` so the
later routers (and their dependencies) can reach them without import cycles.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import AsyncIterator

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.cors import configure_cors
from core.logging import configure_logging, current_request_id
from core.ratelimit import get_limiter
from core.settings import Settings, get_settings
from db.session import dispose_engine, get_engine, get_sessionmaker
from errors import (
    ERROR_INTERNAL,
    ERROR_RATE_LIMITED,
    ERROR_VALIDATION,
    DeltaForgeError,
    ErrorEnvelope,
    FieldError,
)
from models.schemas_wolfram import EngineStatus
from ops.scheduler import AlertSchedulerHandle, start_scheduler, stop_scheduler
from providers.factory import build_market_data_provider
from routers import history_router, portfolios_router, watchlist_router
from routers.alerts import router as alerts_router
from routers.analyze import router as analyze_router
from routers.scenario import router as scenario_router
from routers.trade_ticket import router as trade_ticket_router
from services.wolfram import WolframService
from services.wolfram.service import EngineStatusDTO

logger = logging.getLogger(__name__)

# Shared yfinance + Wolfram thread pool sizing. yfinance calls and the local
# kernel pool both run on this executor; size it for the kernel pool plus a few
# concurrent yfinance fetches (§8.1 cites max_workers=8 for yfinance).
_EXECUTOR_MAX_WORKERS = 8


# ── Meta response models (not part of the §4 split — local to the app) ────────


class HealthResponse(BaseModel):
    """Liveness probe payload (§3 ``GET /health`` → ``HealthResponse``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    version: str


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── EngineStatusDTO → wire EngineStatus mapping (§4.4 / §4.9) ──────────────────


def _engine_status_to_wire(dto: EngineStatusDTO) -> EngineStatus:
    """Map the internal ``EngineStatusDTO`` to the canonical wire model.

    ``ComputeSource`` and ``WolframEngine`` share identical string values
    (§1 rule 2), so the discriminator maps by value.
    """
    return EngineStatus(
        wolfram_available=dto.wolfram_available,
        engine_in_use=dto.engine_in_use.value,  # type: ignore[arg-type]
        kernel_version=dto.kernel_version,
        pool_size=dto.pool_size,
        healthy_sessions=dto.healthy_sessions,
        last_probe_ms=dto.last_probe_ms,
        reason=dto.reason,
        note=dto.note,
        last_checked=dto.last_checked,
    )


# ── Lifespan: construct + dispose shared singletons ───────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construct shared resources on startup; dispose them on shutdown."""
    load_dotenv()

    # Fail-fast on missing required secrets (GROQ_API_KEY, DATABASE_URL).
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("DeltaForge API starting up", extra={"version": app.version})

    # Shared executor for yfinance (off-loop) AND the local Wolfram kernel pool.
    executor = ThreadPoolExecutor(
        max_workers=_EXECUTOR_MAX_WORKERS,
        thread_name_prefix="deltaforge",
    )
    app.state.executor = executor

    # WolframService: construct, start the kernel pool, run a startup health
    # probe. A missing/unstartable kernel degrades to numeric_fallback — it
    # never crashes the boot (§5.2).
    wolfram = WolframService()
    await wolfram.start()
    app.state.wolfram = wolfram
    try:
        probe: EngineStatusDTO = await wolfram.health()
        if probe.wolfram_available:
            logger.info(
                "Wolfram startup probe OK",
                extra={
                    "engine_in_use": probe.engine_in_use.value,
                    "last_probe_ms": probe.last_probe_ms,
                },
            )
        else:
            logger.warning(
                "Wolfram unavailable; running in numeric_fallback",
                extra={"reason": probe.reason},
            )
    except Exception as exc:  # noqa: BLE001 - health must never crash boot
        logger.error("Wolfram startup probe failed", exc_info=True, extra={"error": str(exc)})

    # Market-data provider (WS1 factory). Missing creds fail fast here.
    app.state.market_provider = build_market_data_provider(
        executor,
        provider_name=settings.market_data_provider,
    )

    # Async DB engine + session factory. The engine is lazily created; touch it
    # so a misconfigured DSN surfaces at startup rather than first request.
    get_engine()
    sessionmaker = get_sessionmaker()
    app.state.sessionmaker = sessionmaker

    # WS4: background alert-sweep scheduler. Started only after the shared
    # singletons (wolfram / provider / sessionmaker) exist; each sweep owns its
    # own unit of work (§11.3). A scheduler failure must not crash the boot.
    scheduler_handle: AlertSchedulerHandle | None = None
    try:
        scheduler_handle = start_scheduler(
            sessionmaker=sessionmaker,
            wolfram=wolfram,
            market_provider=app.state.market_provider,
        )
    except Exception:  # noqa: BLE001 - scheduler must never crash the boot
        logger.error("Alert scheduler failed to start", exc_info=True)
    app.state.scheduler = scheduler_handle

    logger.info("DeltaForge API ready")

    try:
        yield
    finally:
        logger.info("DeltaForge API shutting down")
        stop_scheduler(scheduler_handle)
        await wolfram.stop()
        executor.shutdown(wait=False, cancel_futures=True)
        await dispose_engine()


# ── App factory ────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="DeltaForge API",
        version="1.0.0",
        description=(
            "Options risk analysis powered by LangGraph, a local Wolfram Engine "
            "kernel (symbolic, verifiable), and Groq."
        ),
        lifespan=lifespan,
    )

    # CORS from the env allowlist (never "*" — §11.3).
    configure_cors(app)

    # Rate limiting (slowapi). The limiter is attached to app.state per slowapi's
    # contract; the middleware enforces the default limit and per-route limits.
    limiter: Limiter = get_limiter()
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    _register_exception_handlers(app)
    _register_meta_routes(app)

    # Routers that EXIST today (WS3).
    app.include_router(portfolios_router)
    app.include_router(watchlist_router)
    app.include_router(history_router)

    # WS2 routers (analyze pipeline + scenario surface + paper trade ticket).
    # Each reads its shared singletons (WolframService / market provider /
    # sessionmaker) from app.state via Request — no globals, no import cycles.
    app.include_router(analyze_router)
    app.include_router(scenario_router)
    app.include_router(trade_ticket_router)

    # WS4 router (alert CRUD). Firings are written by the background sweep
    # (ops.alert_evaluator), not by this router.
    app.include_router(alerts_router)

    return app


# ── Exception handlers: taxonomy + validation → ErrorEnvelope (§7) ────────────


def _envelope(
    *,
    error: str,
    detail: str,
    status_code: int,
    stage=None,
    field_errors: list[FieldError] | None = None,
) -> JSONResponse:
    """Build a JSONResponse wrapping a canonical ``ErrorEnvelope``."""
    body = ErrorEnvelope(
        error=error,
        detail=detail,
        stage=stage,
        field_errors=field_errors,
        request_id=current_request_id(),
        timestamp=_now(),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _register_exception_handlers(app: FastAPI) -> None:
    """Map the domain taxonomy + framework errors onto ``ErrorEnvelope``."""

    @app.exception_handler(DeltaForgeError)
    async def _domain_error_handler(
        request: Request, exc: DeltaForgeError
    ) -> JSONResponse:
        logger.warning(
            "Domain error",
            extra={
                "path": request.url.path,
                "error_code": exc.error_code,
                "status": exc.status_code,
            },
        )
        return _envelope(
            error=exc.error_code,
            detail=exc.detail,
            status_code=exc.status_code,
            stage=exc.stage,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = [
            FieldError(
                loc=[str(p) for p in err.get("loc", [])],
                msg=str(err.get("msg", "")),
                type=str(err.get("type", "")),
            )
            for err in exc.errors()
        ]
        return _envelope(
            error=ERROR_VALIDATION,
            detail="Request validation failed.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            field_errors=field_errors,
        )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return _envelope(
            error=ERROR_RATE_LIMITED,
            detail=f"Rate limit exceeded: {exc.detail}",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            extra={"path": request.url.path, "error": str(exc)},
            exc_info=True,
        )
        # Generic detail only — never leak stack/secret to the client (§7).
        return _envelope(
            error=ERROR_INTERNAL,
            detail="An internal error occurred.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ── Meta routes: /health + /health/wolfram (§3) ───────────────────────────────


def _register_meta_routes(app: FastAPI) -> None:
    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=app.version)

    @app.get("/health/wolfram", response_model=EngineStatus, tags=["meta"])
    async def health_wolfram(request: Request) -> EngineStatus:
        wolfram: WolframService = request.app.state.wolfram
        dto = await wolfram.health()
        return _engine_status_to_wire(dto)


app = create_app()


# ── Dev entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _settings = get_settings()
    import os

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
        log_config=None,  # our dictConfig owns all logging
    )
