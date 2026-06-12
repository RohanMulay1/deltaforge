"""Portfolio / Greeks / hedging domain package (ARCHITECTURE.md §8.2)."""

from __future__ import annotations

from domain.greeks_aggregation import WeightedLeg, aggregate_portfolio_greeks
from domain.hedging import (
    HEDGE_TARGET_DELTA,
    HedgeTarget,
    compute_hedge_targets,
    delta_to_hedge,
)
from domain.portfolio import (
    EQUITY_MULTIPLIER,
    OPTION_MULTIPLIER,
    Position,
    Side,
)

__all__ = [
    "Position",
    "Side",
    "EQUITY_MULTIPLIER",
    "OPTION_MULTIPLIER",
    "WeightedLeg",
    "aggregate_portfolio_greeks",
    "HEDGE_TARGET_DELTA",
    "HedgeTarget",
    "delta_to_hedge",
    "compute_hedge_targets",
]
