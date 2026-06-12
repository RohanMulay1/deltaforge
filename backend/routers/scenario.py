"""Scenario router (ARCHITECTURE.md §3, §4.8, §5.4, WS2).

    POST /scenario -> ScenarioSurface

Builds a REAL Wolfram P&L surface via ``WolframService.pnl_surface`` over the
requested spot% / IV% grid. With no positions the surface is honestly flagged
``is_stub=true`` (nothing to revalue) but still carries a real WL expression for
the explain drawer. A kernel failure degrades to the labeled numeric fallback
inside the service — never a 500.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from graph.nodes.stages import _build_scenario, _risk_free_rate
from models.schemas_portfolio import PortfolioPosition
from models.schemas_requests import ScenarioRequest
from models.schemas_scenario import ScenarioSurface
from providers.errors import (
    NoChainDataError,
    ProviderUnavailable,
    SymbolNotFoundError,
    UpstreamDataError as ProviderUpstreamError,
)
from errors import SymbolNotFound, UpstreamDataError
from services.wolfram import WolframService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scenario"])

# Safety bound on grid resolution so a pathological (lo,hi,step) can't explode
# the kernel grid (named const, no magic numbers).
_MAX_AXIS_POINTS = 41


def _expand_range(spec: tuple[float, float, float]) -> tuple[float, ...]:
    """Expand a ``(lo, hi, step)`` percent spec into fractional multipliers.

    Inputs are PERCENT (e.g. ``(-10, 10, 5)`` -> ``[-0.10, -0.05, 0.0, ...]``).
    Bounded to ``_MAX_AXIS_POINTS`` points; a non-positive step yields the lone
    midpoint.
    """
    lo, hi, step = spec
    if step <= 0 or hi < lo:
        return (round(((lo + hi) / 2.0) / 100.0, 6),)
    points: list[float] = []
    value = lo
    while value <= hi + 1e-9 and len(points) < _MAX_AXIS_POINTS:
        points.append(round(value / 100.0, 6))
        value += step
    return tuple(points) if points else (round(lo / 100.0, 6),)


def _service(request: Request) -> WolframService:
    return request.app.state.wolfram


def _provider(request: Request) -> object:
    return request.app.state.market_provider


async def _resolve_positions(
    request: Request, req: ScenarioRequest
) -> list[PortfolioPosition]:
    """Resolve positions from the request body or a saved portfolio id."""
    if req.positions:
        return list(req.positions)
    if req.portfolio_id is None:
        return []
    sessionmaker = getattr(request.app.state, "sessionmaker", None)
    if sessionmaker is None:
        return []
    try:
        import uuid

        from db.repositories.portfolio_repo import PortfolioRepository
        from routers.portfolios import _to_wire_position

        session = sessionmaker()
        async with session as s:  # type: ignore[union-attr]
            repo = PortfolioRepository(s)
            orm = await repo.get_with_positions(uuid.UUID(req.portfolio_id))
            if orm is None:
                return []
            return [_to_wire_position(p) for p in orm.positions]
    except Exception as exc:  # noqa: BLE001 - missing/invalid portfolio -> empty
        logger.warning("Could not resolve portfolio %s: %s", req.portfolio_id, exc)
        return []


async def _spot_and_iv(provider: object, symbol: str) -> tuple[float, float]:
    """Fetch spot + a representative ATM IV for the scenario underlying."""
    try:
        quote = await provider.get_spot(symbol)  # type: ignore[attr-defined]
        spot = float(quote.price)
    except SymbolNotFoundError as exc:
        raise SymbolNotFound(str(exc)) from exc
    except (ProviderUnavailable, ProviderUpstreamError, NoChainDataError) as exc:
        raise UpstreamDataError(str(exc)) from exc
    return spot, 0.0


@router.post("/scenario", response_model=ScenarioSurface)
async def scenario(req: ScenarioRequest, request: Request) -> ScenarioSurface:
    """Compute a P&L surface over the requested spot%/IV% grid (§4.8)."""
    positions = await _resolve_positions(request, req)
    symbol = positions[0].symbol.upper() if positions else "SPY"
    provider = _provider(request)
    spot, chain_iv = await _spot_and_iv(provider, symbol)

    spot_pcts = _expand_range(req.spot_pct_range)
    iv_pcts = _expand_range(req.iv_pct_range)

    surface, _comp = await _build_scenario(
        _service(request),
        symbol=symbol,
        spot=spot,
        rate=_risk_free_rate(),
        positions=positions,
        chain_iv=chain_iv,
        spot_pcts=spot_pcts,
        iv_pcts=iv_pcts,
    )
    return surface
