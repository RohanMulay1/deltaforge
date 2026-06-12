"""DeltaForge pipeline state (ARCHITECTURE.md §4, §5, §6, WS2).

``GraphState`` is the immutable-by-convention container that flows through the
canonical pipeline stages:

    market_data -> greeks -> portfolio -> hedge -> scenario -> summary

It carries the WS0 wire models (``MarketSnapshot``, ``PortfolioGreeks``,
``HedgeRecommendation``, ``ScenarioSurface``) plus the accumulated
``wolfram_computations`` provenance list and the active ``EngineStatus``. Nodes
NEVER mutate the dict in place — each returns a NEW ``GraphState`` produced by
``advance(state, **delta)`` (immutability rule).

This module intentionally has no I/O and no kernel/provider imports; it is the
pure data contract between nodes. The execution logic lives in
``graph.nodes.stages`` and ``graph.pipeline``.
"""

from __future__ import annotations

from typing import Optional

from typing_extensions import TypedDict

from models.schemas_market import MarketSnapshot
from models.schemas_portfolio import PortfolioGreeks, PortfolioPosition
from models.schemas_hedge import HedgeRecommendation
from models.schemas_scenario import ScenarioSurface
from models.schemas_wolfram import EngineStatus, WolframComputation


class GraphState(TypedDict, total=False):
    """State container shared across all DeltaForge pipeline stages.

    ``total=False`` so a partially-built state (e.g. after only ``market_data``)
    is still a valid ``GraphState``. ``symbol`` and ``dte_max`` are always set by
    the seed; every other key is filled as its stage completes.
    """

    # ── Inputs (set before the pipeline runs) ─────────────────────────────────
    symbol: str
    dte_max: int
    positions: Optional[list[PortfolioPosition]]

    # ── Stage outputs (canonical wire models) ─────────────────────────────────
    market: Optional[MarketSnapshot]
    portfolio_greeks: Optional[PortfolioGreeks]
    hedge: Optional[HedgeRecommendation]
    scenario: Optional[ScenarioSurface]
    risk_summary: Optional[str]

    # ── Provenance + engine ───────────────────────────────────────────────────
    wolfram_computations: list[WolframComputation]
    engine_status: Optional[EngineStatus]
    wolfram_computation_used: str

    # ── Control / diagnostics ─────────────────────────────────────────────────
    error: Optional[str]


def seed_state(
    symbol: str,
    dte_max: int,
    positions: Optional[list[PortfolioPosition]],
) -> GraphState:
    """Build the initial ``GraphState`` for a run (pure)."""
    return GraphState(
        symbol=symbol.upper().strip(),
        dte_max=dte_max,
        positions=positions,
        market=None,
        portfolio_greeks=None,
        hedge=None,
        scenario=None,
        risk_summary=None,
        wolfram_computations=[],
        engine_status=None,
        wolfram_computation_used="",
        error=None,
    )


def advance(state: GraphState, **delta: object) -> GraphState:
    """Return a NEW ``GraphState`` with ``delta`` applied (never mutate input).

    ``wolfram_computations`` is treated as append-only: passing
    ``wolfram_computations=[...]`` REPLACES it, so callers that want to append
    must build the new list themselves (``[*state["wolfram_computations"], c]``).
    """
    new_state: GraphState = dict(state)  # type: ignore[assignment]
    new_state.update(delta)  # type: ignore[typeddict-item]
    return new_state
