"""Source-agnostic options analytics (ARCHITECTURE.md §8.1).

Order-flow imbalance and pin-risk score, extracted verbatim (behaviour-wise)
from the legacy ``market_data_agent.py`` so they no longer couple to yfinance or
to any provider. Every function is pure and operates on minimal structural
inputs (anything exposing ``volume`` / ``open_interest`` / ``strike``), making
them trivially unit-testable.

These also accept the provider's ``RawContract`` DTOs directly.
"""

from __future__ import annotations

from typing import Protocol

# Pin-risk proximity window: ±10% of spot is the normalising band.
PIN_RISK_WINDOW_PCT = 0.10
_ROUND_DP = 4


class _HasFlow(Protocol):
    """Anything carrying a non-negative ``volume`` (source-agnostic)."""

    volume: int


class _HasOI(Protocol):
    """Anything carrying ``open_interest`` and a ``strike`` (source-agnostic)."""

    open_interest: int
    strike: float


def compute_order_flow_imbalance(
    calls: list[_HasFlow] | tuple[_HasFlow, ...],
    puts: list[_HasFlow] | tuple[_HasFlow, ...],
) -> float:
    """Signed call/put volume imbalance in ``[-1, 1]``.

    ``+1`` = all call volume, ``-1`` = all put volume, ``0`` = balanced or empty.
    """
    call_volume = sum(c.volume for c in calls)
    put_volume = sum(p.volume for p in puts)
    total = call_volume + put_volume
    if total == 0:
        return 0.0
    return round((call_volume - put_volume) / total, _ROUND_DP)


def compute_pin_risk_score(
    calls: list[_HasOI] | tuple[_HasOI, ...],
    puts: list[_HasOI] | tuple[_HasOI, ...],
    spot_price: float,
) -> float:
    """Score in ``[0, 1]`` for how close the max-OI strike sits to spot.

    ``1.0`` = max-OI strike equals spot (maximum pin risk); ``0.0`` = the
    max-OI strike is at/beyond the ±10% window. Empty chain or non-positive
    spot ⇒ ``0.0``.
    """
    all_contracts = list(calls) + list(puts)
    if not all_contracts or spot_price <= 0.0:
        return 0.0

    max_oi_contract = max(all_contracts, key=lambda c: c.open_interest)
    distance = abs(max_oi_contract.strike - spot_price)
    window = spot_price * PIN_RISK_WINDOW_PCT
    score = max(0.0, 1.0 - (distance / window))
    return round(min(score, 1.0), _ROUND_DP)


def compute_max_pain_strike(
    calls: list[_HasOI] | tuple[_HasOI, ...],
    puts: list[_HasOI] | tuple[_HasOI, ...],
) -> float:
    """The strike with the greatest combined open interest (max-pain proxy).

    Returns ``0.0`` for an empty chain. This is the OI-weighted pin magnet used
    by ``MarketSnapshot.max_pain_strike``.
    """
    oi_by_strike: dict[float, int] = {}
    for contract in list(calls) + list(puts):
        oi_by_strike[contract.strike] = (
            oi_by_strike.get(contract.strike, 0) + contract.open_interest
        )
    if not oi_by_strike:
        return 0.0
    return max(oi_by_strike.items(), key=lambda kv: kv[1])[0]
