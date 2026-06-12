"""Source-agnostic analytics tests (ARCHITECTURE.md §8.1)."""

from __future__ import annotations

from dataclasses import dataclass

from analytics import (
    PIN_RISK_WINDOW_PCT,
    compute_max_pain_strike,
    compute_order_flow_imbalance,
    compute_pin_risk_score,
)


@dataclass(frozen=True)
class _Flow:
    volume: int


@dataclass(frozen=True)
class _OI:
    open_interest: int
    strike: float


# ── order-flow imbalance ──────────────────────────────────────────────────────


def test_ofi_all_calls_is_plus_one() -> None:
    assert compute_order_flow_imbalance([_Flow(100)], []) == 1.0


def test_ofi_all_puts_is_minus_one() -> None:
    assert compute_order_flow_imbalance([], [_Flow(100)]) == -1.0


def test_ofi_balanced_is_zero() -> None:
    assert compute_order_flow_imbalance([_Flow(50)], [_Flow(50)]) == 0.0


def test_ofi_empty_is_zero() -> None:
    assert compute_order_flow_imbalance([], []) == 0.0


def test_ofi_partial_imbalance() -> None:
    # 75 call / 25 put -> (75-25)/100 = 0.5
    assert compute_order_flow_imbalance([_Flow(75)], [_Flow(25)]) == 0.5


def test_ofi_stays_in_band() -> None:
    value = compute_order_flow_imbalance([_Flow(1000)], [_Flow(1)])
    assert -1.0 <= value <= 1.0


# ── pin-risk score ────────────────────────────────────────────────────────────


def test_pin_risk_max_when_max_oi_strike_equals_spot() -> None:
    calls = [_OI(open_interest=10_000, strike=500.0)]
    assert compute_pin_risk_score(calls, [], spot_price=500.0) == 1.0


def test_pin_risk_zero_at_window_edge() -> None:
    spot = 500.0
    edge_strike = spot + spot * PIN_RISK_WINDOW_PCT  # exactly at the +10% edge
    calls = [_OI(open_interest=10_000, strike=edge_strike)]
    assert compute_pin_risk_score(calls, [], spot_price=spot) == 0.0


def test_pin_risk_zero_when_empty() -> None:
    assert compute_pin_risk_score([], [], spot_price=500.0) == 0.0


def test_pin_risk_zero_when_spot_non_positive() -> None:
    calls = [_OI(open_interest=10_000, strike=500.0)]
    assert compute_pin_risk_score(calls, [], spot_price=0.0) == 0.0


def test_pin_risk_uses_max_oi_contract() -> None:
    # The 5000-OI strike sits at spot; a tiny-OI strike far away is ignored.
    calls = [_OI(open_interest=5000, strike=500.0), _OI(open_interest=1, strike=600.0)]
    assert compute_pin_risk_score(calls, [], spot_price=500.0) == 1.0


def test_pin_risk_in_band() -> None:
    calls = [_OI(open_interest=100, strike=502.5)]
    score = compute_pin_risk_score(calls, [], spot_price=500.0)
    assert 0.0 < score < 1.0


# ── max pain ──────────────────────────────────────────────────────────────────


def test_max_pain_picks_greatest_combined_oi() -> None:
    calls = [_OI(open_interest=100, strike=510.0), _OI(open_interest=900, strike=520.0)]
    puts = [_OI(open_interest=300, strike=520.0)]
    # strike 520 total OI = 900 + 300 = 1200 > 510 (100)
    assert compute_max_pain_strike(calls, puts) == 520.0


def test_max_pain_empty_is_zero() -> None:
    assert compute_max_pain_strike([], []) == 0.0
