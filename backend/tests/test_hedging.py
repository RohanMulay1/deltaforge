"""Hedging domain tests (ARCHITECTURE.md §8.2)."""

from __future__ import annotations

from domain.greeks_aggregation import WeightedLeg
from domain.hedging import (
    HEDGE_TARGET_DELTA,
    compute_hedge_targets,
    delta_to_hedge,
)
from domain.portfolio import OPTION_MULTIPLIER
from models.schemas_greeks import Greeks


def _half_delta_call() -> Greeks:
    return Greeks(delta=0.5, gamma=0.01, theta=0.0, vega=0.0, rho=0.0)


# ── delta_to_hedge ────────────────────────────────────────────────────────────


def test_delta_to_hedge_is_target_minus_net() -> None:
    assert delta_to_hedge(250.0) == HEDGE_TARGET_DELTA - 250.0
    assert delta_to_hedge(250.0) == -250.0


def test_delta_to_hedge_custom_target() -> None:
    assert delta_to_hedge(100.0, delta_target=50.0) == -50.0


def test_delta_to_hedge_negative_net() -> None:
    assert delta_to_hedge(-80.0) == 80.0


# ── compute_hedge_targets ─────────────────────────────────────────────────────


def test_empty_legs_yields_no_targets() -> None:
    assert compute_hedge_targets([], {}, {}) == []


def test_single_symbol_target() -> None:
    legs = [WeightedLeg("p1", 5 * OPTION_MULTIPLIER, _half_delta_call())]  # +250
    targets = compute_hedge_targets(
        legs, {"p1": "SPY"}, {"SPY": 500.0}
    )
    assert len(targets) == 1
    target = targets[0]
    assert target.symbol == "SPY"
    assert target.net_delta == 250.0
    assert target.delta_to_hedge == -250.0
    assert target.has_exposure is True


def test_multi_symbol_groups_by_underlying() -> None:
    legs = [
        WeightedLeg("spy1", 5 * OPTION_MULTIPLIER, _half_delta_call()),  # SPY +250
        WeightedLeg("qqq1", -2 * OPTION_MULTIPLIER, _half_delta_call()),  # QQQ -100
    ]
    symbols = {"spy1": "SPY", "qqq1": "QQQ"}
    targets = compute_hedge_targets(legs, symbols, {"SPY": 500.0, "QQQ": 400.0})
    by_symbol = {t.symbol: t for t in targets}
    assert by_symbol["SPY"].net_delta == 250.0
    assert by_symbol["QQQ"].net_delta == -100.0


def test_zero_net_delta_has_no_exposure() -> None:
    legs = [
        WeightedLeg("a", 5 * OPTION_MULTIPLIER, _half_delta_call()),
        WeightedLeg("b", -5 * OPTION_MULTIPLIER, _half_delta_call()),
    ]
    targets = compute_hedge_targets(
        legs, {"a": "SPY", "b": "SPY"}, {"SPY": 500.0}
    )
    assert len(targets) == 1
    assert targets[0].net_delta == 0.0
    assert targets[0].has_exposure is False


def test_unmapped_leg_is_skipped() -> None:
    legs = [WeightedLeg("orphan", 1 * OPTION_MULTIPLIER, _half_delta_call())]
    targets = compute_hedge_targets(legs, {}, {})  # no symbol mapping
    assert targets == []


def test_target_carries_explicit_delta_target() -> None:
    legs = [WeightedLeg("p1", 1 * OPTION_MULTIPLIER, _half_delta_call())]
    targets = compute_hedge_targets(
        legs, {"p1": "SPY"}, {"SPY": 500.0}, delta_target=10.0
    )
    assert targets[0].delta_target == 10.0
    assert targets[0].delta_to_hedge == 10.0 - 50.0
