"""Hedging domain logic (ARCHITECTURE.md §8.2).

Computes the REAL delta to neutralize per underlying. ``delta_to_hedge =
HEDGE_TARGET_DELTA - net_delta`` where ``net_delta`` is the aggregated portfolio
delta for that underlying. Multi-symbol portfolios hedge **per underlying**
(legs grouped by ``symbol``). An empty portfolio (or an underlying with zero net
delta) produces an explicit "no exposure" state — never a fake 1-contract trade.

The actual NMinimize optimization lives in ``WolframService.delta_neutral_hedge``;
this module produces its inputs (the per-underlying target) and the honest
"no-exposure" short-circuit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from domain.greeks_aggregation import WeightedLeg, aggregate_portfolio_greeks

# Configurable delta target. Surfaced explicitly (§1 rule 7) — never a silent 0.
HEDGE_TARGET_DELTA = 0.0

# Net delta below this magnitude is treated as "no exposure" (floating-point
# dust from summation should not trigger a hedge).
_NO_EXPOSURE_EPS = 1e-9


@dataclass(frozen=True)
class HedgeTarget:
    """The per-underlying hedging objective.

    ``delta_to_hedge`` is the delta the hedge must *add* to reach the target:
    ``HEDGE_TARGET_DELTA - net_delta``. ``has_exposure`` is ``False`` when the
    underlying has effectively zero net delta (explicit no-op state).
    """

    symbol: str
    net_delta: float
    delta_target: float
    delta_to_hedge: float
    has_exposure: bool


def _group_legs_by_symbol(legs: Sequence[WeightedLeg], symbols: Mapping[str, str]) -> dict[str, list[WeightedLeg]]:
    """Group weighted legs by their underlying symbol.

    ``symbols`` maps ``position_id → underlying symbol`` (a ``WeightedLeg`` does
    not itself carry the symbol). Legs with no mapping are skipped.
    """
    grouped: dict[str, list[WeightedLeg]] = {}
    for leg in legs:
        symbol = symbols.get(leg.position_id)
        if symbol is None:
            continue
        grouped.setdefault(symbol, []).append(leg)
    return grouped


def delta_to_hedge(net_delta: float, *, delta_target: float = HEDGE_TARGET_DELTA) -> float:
    """The signed delta a hedge must add to reach ``delta_target``.

    ``delta_to_hedge = delta_target - net_delta``.
    """
    return delta_target - net_delta


def compute_hedge_targets(
    legs: Sequence[WeightedLeg],
    symbols: Mapping[str, str],
    spot_by_symbol: Mapping[str, float],
    *,
    delta_target: float = HEDGE_TARGET_DELTA,
) -> list[HedgeTarget]:
    """Per-underlying hedge targets for a (possibly multi-symbol) portfolio.

    Args:
        legs: weighted legs (from ``greeks_aggregation``).
        symbols: ``position_id → underlying symbol``.
        spot_by_symbol: ``symbol → spot price`` (only used to aggregate dollars).
        delta_target: the explicit target delta (default ``HEDGE_TARGET_DELTA``).

    Returns:
        One ``HedgeTarget`` per underlying with non-empty legs. An empty
        ``legs`` sequence returns ``[]`` — the explicit "no exposure" state.
    """
    grouped = _group_legs_by_symbol(legs, symbols)
    targets: list[HedgeTarget] = []
    for symbol, symbol_legs in grouped.items():
        spot = spot_by_symbol.get(symbol, 0.0)
        agg = aggregate_portfolio_greeks(symbol_legs, spot)
        net = agg.delta
        to_hedge = delta_to_hedge(net, delta_target=delta_target)
        targets.append(
            HedgeTarget(
                symbol=symbol,
                net_delta=net,
                delta_target=delta_target,
                delta_to_hedge=to_hedge,
                has_exposure=abs(net) > _NO_EXPOSURE_EPS,
            )
        )
    return targets
