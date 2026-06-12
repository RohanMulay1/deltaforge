"""Analyze router (ARCHITECTURE.md §3, §6, WS2).

Endpoints:
    POST /analyze            -> AnalyzeResponse        (full pipeline, §4.10)
    GET  /analyze/stream     -> text/event-stream      (SSE per §6)
    POST /portfolio/greeks   -> PortfolioGreeks        (debounced aggregate)

Shared singletons (``WolframService``, market provider, sessionmaker) are read
from ``app.state`` where the lifespan placed them — no import cycles, no globals.
A Wolfram failure degrades to ``numeric_fallback`` inside the service; it never
500s here. Persistence is best-effort (a DB outage still returns the analysis).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from graph.pipeline import (
    aggregate_position_greeks,
    analysis_event_stream,
    run_analysis,
)
from models.schemas_analyze import AnalyzeResponse
from models.schemas_portfolio import PortfolioGreeks, PortfolioPosition
from models.schemas_requests import AnalyzeRequest
from providers.errors import (
    NoChainDataError,
    ProviderUnavailable,
    SymbolNotFoundError,
    UpstreamDataError as ProviderUpstreamError,
)
from errors import SymbolNotFound, UpstreamDataError
from services.wolfram import WolframService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyze"])


# ── Router-local request model for /portfolio/greeks (§3, not in WS0 §4) ──────


class GreeksRequest(BaseModel):
    """Debounced aggregate-greeks request from the portfolio rail (§3)."""

    model_config = ConfigDict(extra="forbid")

    positions: list[PortfolioPosition] = Field(default_factory=list)
    symbol: str = Field(min_length=1, max_length=8)
    dte_max: int = Field(default=7, ge=1, le=365)
    spot_price: float | None = Field(default=None, gt=0.0)


# ── State accessors ───────────────────────────────────────────────────────────


def _service(request: Request) -> WolframService:
    return request.app.state.wolfram


def _provider(request: Request) -> object:
    return request.app.state.market_provider


def _sessionmaker(request: Request) -> object | None:
    return getattr(request.app.state, "sessionmaker", None)


async def _spot_for(provider: object, symbol: str, override: float | None) -> float:
    """Resolve the spot price for greeks pricing (provider lookup or override)."""
    if override is not None:
        return override
    try:
        quote = await provider.get_spot(symbol)  # type: ignore[attr-defined]
        return float(quote.price)
    except SymbolNotFoundError as exc:
        raise SymbolNotFound(str(exc)) from exc
    except (ProviderUnavailable, ProviderUpstreamError, NoChainDataError) as exc:
        raise UpstreamDataError(str(exc)) from exc


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    """Run the full pipeline and return the canonical ``AnalyzeResponse``."""
    return await run_analysis(
        req,
        service=_service(request),
        provider=_provider(request),
        sessionmaker=_sessionmaker(request),
    )


@router.get("/analyze/stream")
async def analyze_stream(
    request: Request,
    symbol: str = Query(min_length=1, max_length=8, pattern=r"^[A-Za-z.\-]+$"),
    dte_max: int = Query(default=7, ge=1, le=365),
    portfolio_id: str | None = Query(default=None),
) -> StreamingResponse:
    """Stream the analysis as SSE (§6).

    ``portfolio_id`` is accepted for forward compatibility (positions sourced
    from a saved portfolio); positions are not yet hydrated from it here, so the
    stream runs the market-side pipeline with an empty book unless extended.
    """
    req = AnalyzeRequest(symbol=symbol, dte_max=dte_max, positions=None)
    stream = analysis_event_stream(
        req,
        service=_service(request),
        provider=_provider(request),
        sessionmaker=_sessionmaker(request),
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering for SSE
        },
    )


@router.post("/portfolio/greeks", response_model=PortfolioGreeks)
async def portfolio_greeks(body: GreeksRequest, request: Request) -> PortfolioGreeks:
    """Aggregate Greeks for posted positions without the full pipeline (§3)."""
    provider = _provider(request)
    spot = await _spot_for(provider, body.symbol.upper(), body.spot_price)
    return await aggregate_position_greeks(
        body.positions,
        symbol=body.symbol.upper(),
        spot=spot,
        service=_service(request),
    )
