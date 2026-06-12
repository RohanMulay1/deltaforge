"""Market data models (ARCHITECTURE.md §4.5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .schemas_common import OptionType
from .schemas_greeks import Greeks
from .schemas_wolfram import WolframComputation


class OptionQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strike: float
    type: OptionType
    expiry: str  # YYYY-MM-DD
    bid: float
    ask: float
    last_price: float
    volume: int = Field(ge=0)
    open_interest: int = Field(ge=0)
    iv: float = Field(ge=0.0)  # decimal (0.18 = 18%)
    ofi: float = Field(ge=-1.0, le=1.0)
    greeks: Greeks
    delta: float  # convenience mirror of greeks.delta
    moneyness: float  # spot/strike
    wolfram: WolframComputation | None = None


class IVStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    iv_rank: float = Field(ge=0.0, le=100.0)
    iv_percentile: float = Field(ge=0.0, le=100.0)
    atm_iv: float
    iv_30d_high: float
    iv_30d_low: float
    term_structure: list[tuple[str, float]] = Field(default_factory=list)


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    spot_price: float
    timestamp: datetime
    expiry_used: str
    near_expiry_filter_used: str
    dte: int
    order_flow_imbalance: float = Field(ge=-1.0, le=1.0)
    pin_risk_score: float = Field(ge=0.0, le=1.0)
    max_pain_strike: float
    iv_stats: IVStats
    calls_count: int
    puts_count: int
    chain: list[OptionQuote]
    data_source: str = "yfinance"  # provider .name → provenance
