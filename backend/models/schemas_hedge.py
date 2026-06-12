"""Hedge recommendation model (ARCHITECTURE.md §4.7)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .schemas_common import OptionType
from .schemas_wolfram import WolframComputation


class HedgeRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    delta_neutral_ratio: float
    contracts_to_trade: int
    option_type_to_trade: OptionType
    strike_to_trade: float
    expiry_to_trade: str
    expected_pnl_range: tuple[float, float]
    current_portfolio_delta: float  # the REAL delta being neutralized
    residual_delta_after_hedge: float
    delta_target: float  # explicit, surfaced (not silent 0)
    wolfram_computation_used: str  # legacy combined WL string (UI still renders)
    wolfram: WolframComputation  # structured NMinimize provenance
    reasoning: str
