"""Legacy ``models.schemas`` compatibility shim.

The canonical contract now lives in the focused ``models/schemas_*.py`` files
(ARCHITECTURE.md §4), re-exported from ``models/__init__.py``. This module is a
THIN SHIM kept alive only so the not-yet-rewritten legacy graph
(``graph/pipeline.py``, ``graph/state.py``) and ``agents/market_data_agent.py``
keep importing. WS2 deletes this file when it rewrites the pipeline against the
canonical models.

It does two things:

  1. Re-exports the canonical names so ``from models.schemas import Greeks`` (and
     every other §4 model) resolves to the single source of truth.
  2. Preserves the legacy ``OptionContract`` / ``OptionsChainPayload`` /
     ``WolframRiskInput`` / legacy ``HedgeRecommendation`` shapes the old
     pipeline still depends on. The canonical §4.7 hedge model is also exported,
     unambiguously, as ``CanonicalHedgeRecommendation``.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, field_validator

# ── Canonical re-exports (single source of truth: models/__init__.py) ─────────
from models import (  # noqa: F401  (re-exported for compatibility)
    AlertCreate,
    AnalyzeRequest,
    AnalyzeResponse,
    CsvImportRequest,
    CsvImportResult,
    CsvRowError,
    EngineStatus,
    Greeks,
    InstrumentType,
    IVStats,
    MarketSnapshot,
    OptionQuote,
    OptionType,
    PipelineStage,
    Portfolio,
    PortfolioCreate,
    PortfolioGreeks,
    PortfolioPosition,
    ScenarioAxis,
    ScenarioSurface,
    WolframComputation,
    WolframEngine,
)
from models import HedgeRecommendation as CanonicalHedgeRecommendation  # noqa: F401


# ── Legacy models (DEPRECATED — consumed only by the not-yet-rewritten graph) ──


class OptionContract(BaseModel):
    """DEPRECATED legacy contract. Use ``OptionQuote`` (§4.5)."""

    strike: float
    expiry: str  # ISO date string YYYY-MM-DD
    option_type: str  # "call" or "put"
    bid: float
    ask: float
    last_price: float
    volume: int
    open_interest: int
    implied_volatility: float = Field(ge=0.0)

    @field_validator("option_type")
    @classmethod
    def validate_option_type(cls, v: str) -> str:
        if v not in ("call", "put"):
            raise ValueError(f"option_type must be 'call' or 'put', got '{v}'")
        return v


class OptionsChainPayload(BaseModel):
    """DEPRECATED legacy chain payload. Use ``MarketSnapshot`` (§4.5)."""

    symbol: str
    spot_price: float
    timestamp: datetime
    expiry_used: str
    near_expiry_filter_used: str
    calls: List[OptionContract]
    puts: List[OptionContract]
    order_flow_imbalance: float = Field(
        description="(call_volume - put_volume) / (call_volume + put_volume); range [-1, 1]"
    )
    pin_risk_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Proximity of max-OI strike to spot, normalized to [0, 1]",
    )


class WolframRiskInput(OptionsChainPayload):
    """DEPRECATED legacy risk input."""

    risk_free_rate: float = Field(
        default=0.053, description="Current US 3-month T-bill rate"
    )
    portfolio_delta_target: float = Field(
        default=0.0, description="Target portfolio delta for hedge"
    )


class HedgeRecommendation(BaseModel):
    """DEPRECATED legacy hedge model. Canonical: ``CanonicalHedgeRecommendation``."""

    symbol: str
    delta_neutral_ratio: float
    contracts_to_trade: int
    option_type_to_trade: str  # "call" or "put"
    strike_to_trade: float
    expiry_to_trade: str
    expected_pnl_range: tuple[float, float]
    wolfram_computation_used: str
    reasoning: str
