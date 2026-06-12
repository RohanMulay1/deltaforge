"""Portfolio models (ARCHITECTURE.md §4.6).

Position quantity is a SIGNED int on the wire (§1 rule 6); negative = short.
There is no ``side`` field crossing the wire.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .schemas_common import InstrumentType
from .schemas_greeks import Greeks
from .schemas_wolfram import WolframComputation


class PortfolioPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str | None = None
    symbol: str
    instrument: InstrumentType = InstrumentType.CALL
    strike: float | None = None  # required iff option
    expiry: str | None = None  # required iff option
    quantity: int  # SIGNED; negative = short (canonical, no `side`)
    avg_price: float | None = None
    greeks: Greeks | None = None  # filled after pricing
    wolfram: WolframComputation | None = None


class PortfolioGreeks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float = 0.0
    net_delta_dollars: float  # delta × spot × 100 × contracts
    beta_weighted_delta: float | None = None
    per_position: dict[str, Greeks] = Field(default_factory=dict)  # position_id → greeks
    wolfram: WolframComputation | None = None


class Portfolio(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    positions: list[PortfolioPosition]
    created_at: datetime
    updated_at: datetime
