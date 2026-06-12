"""Pure portfolio-Greeks aggregation tests (ARCHITECTURE.md §8.2).

Acceptance (WS1): long 5 ATM 0.5Δ calls ⇒ +250 net delta; short subtracts;
equity multiplier 1 vs option 100; empty ⇒ all-zero.
"""

from __future__ import annotations

from domain.greeks_aggregation import (
    WeightedLeg,
    aggregate_portfolio_greeks,
)
from domain.portfolio import EQUITY_MULTIPLIER, OPTION_MULTIPLIER
from models.schemas_greeks import Greeks

_SPOT = 500.0


def _half_delta_call() -> Greeks:
    return Greeks(delta=0.5, gamma=0.01, theta=-0.02, vega=0.1, rho=0.05)


def test_long_five_atm_half_delta_calls_is_plus_250() -> None:
    # weight = signed_qty(5) * OPTION_MULTIPLIER(100) = 500; 500 * 0.5Δ = 250.
    leg = WeightedLeg(
        position_id="c1",
        weight=5 * OPTION_MULTIPLIER,
        per_unit=_half_delta_call(),
    )
    agg = aggregate_portfolio_greeks([leg], _SPOT)
    assert agg.delta == 250.0


def test_short_position_subtracts_delta() -> None:
    leg = WeightedLeg(
        position_id="c1",
        weight=-5 * OPTION_MULTIPLIER,  # short 5
        per_unit=_half_delta_call(),
    )
    agg = aggregate_portfolio_greeks([leg], _SPOT)
    assert agg.delta == -250.0


def test_long_and_short_net_to_zero() -> None:
    long_leg = WeightedLeg("a", 5 * OPTION_MULTIPLIER, _half_delta_call())
    short_leg = WeightedLeg("b", -5 * OPTION_MULTIPLIER, _half_delta_call())
    agg = aggregate_portfolio_greeks([long_leg, short_leg], _SPOT)
    assert agg.delta == 0.0


def test_equity_multiplier_is_one() -> None:
    # 100 shares of equity (delta 1) -> weight 100 * 1, delta 100.
    leg = WeightedLeg(
        position_id="e1",
        weight=100 * EQUITY_MULTIPLIER,
        per_unit=Greeks(delta=1.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0),
    )
    agg = aggregate_portfolio_greeks([leg], _SPOT)
    assert agg.delta == 100.0
    assert agg.gamma == 0.0


def test_option_multiplier_is_hundred_vs_equity() -> None:
    option_leg = WeightedLeg("o", 1 * OPTION_MULTIPLIER, _half_delta_call())
    equity_leg = WeightedLeg(
        "e",
        1 * EQUITY_MULTIPLIER,
        Greeks(delta=1.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0),
    )
    option_delta = aggregate_portfolio_greeks([option_leg], _SPOT).delta
    equity_delta = aggregate_portfolio_greeks([equity_leg], _SPOT).delta
    assert option_delta == 50.0  # 100 * 0.5
    assert equity_delta == 1.0


def test_empty_portfolio_is_all_zero() -> None:
    agg = aggregate_portfolio_greeks([], _SPOT)
    assert agg.delta == 0.0
    assert agg.gamma == 0.0
    assert agg.theta == 0.0
    assert agg.vega == 0.0
    assert agg.rho == 0.0
    assert agg.net_delta_dollars == 0.0
    assert agg.per_position == {}


def test_net_delta_dollars_is_delta_times_spot() -> None:
    leg = WeightedLeg("c1", 5 * OPTION_MULTIPLIER, _half_delta_call())
    agg = aggregate_portfolio_greeks([leg], _SPOT)
    assert agg.net_delta_dollars == 250.0 * _SPOT


def test_all_greeks_aggregate() -> None:
    leg = WeightedLeg("c1", 2 * OPTION_MULTIPLIER, _half_delta_call())  # weight 200
    agg = aggregate_portfolio_greeks([leg], _SPOT)
    assert agg.gamma == 200 * 0.01
    assert agg.theta == 200 * -0.02
    assert agg.vega == 200 * 0.1
    assert agg.rho == 200 * 0.05


def test_per_position_breakdown_present() -> None:
    leg = WeightedLeg("c1", 2 * OPTION_MULTIPLIER, _half_delta_call())
    agg = aggregate_portfolio_greeks([leg], _SPOT)
    assert "c1" in agg.per_position
    assert agg.per_position["c1"].delta == 200 * 0.5


def test_beta_weighted_delta_applied() -> None:
    leg = WeightedLeg("c1", 1 * OPTION_MULTIPLIER, _half_delta_call())
    agg = aggregate_portfolio_greeks([leg], _SPOT, beta_weights={"c1": 2.0})
    # leg_delta = 100 * 0.5 = 50; beta_delta = 50 * 2.0 = 100.
    assert agg.beta_weighted_delta == 100.0


def test_beta_weighted_delta_none_when_omitted() -> None:
    leg = WeightedLeg("c1", 1 * OPTION_MULTIPLIER, _half_delta_call())
    agg = aggregate_portfolio_greeks([leg], _SPOT)
    assert agg.beta_weighted_delta is None
