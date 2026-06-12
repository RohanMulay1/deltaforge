"""Top-level /analyze response — the whole dashboard (ARCHITECTURE.md §4.10)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .schemas_hedge import HedgeRecommendation
from .schemas_market import MarketSnapshot, OptionQuote
from .schemas_portfolio import PortfolioGreeks
from .schemas_scenario import ScenarioSurface
from .schemas_wolfram import EngineStatus, WolframComputation

_DISCLAIMER = "Informational only. Not investment advice. No live execution."


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # identity / HUD scalars
    symbol: str
    spot_price: float
    expiry: str
    calls_count: int
    puts_count: int
    order_flow_imbalance: float
    pin_risk_score: float
    iv_rank: float  # = market.iv_stats.iv_rank (was hardcoded 0)

    # full renderable payloads
    market: MarketSnapshot  # chain + iv_stats
    options_chain: list[OptionQuote]  # mirror of market.chain (UI reads top-level)
    portfolio_greeks: PortfolioGreeks  # HUD Delta/Gamma/Theta (was all 0)
    hedge: HedgeRecommendation
    scenario: ScenarioSurface  # stub in P0

    # narrative + provenance
    risk_summary: str
    wolfram_computation_used: str  # legacy top-level string
    wolfram_computations: list[WolframComputation]  # every expr this run
    engine_status: EngineStatus
    analysis_id: str | None = None  # set once persisted (P3)
    generated_at: datetime
    disclaimer: str = _DISCLAIMER
