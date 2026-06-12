"""Pure mapper tests (graph/nodes/builders.py — ARCHITECTURE.md §4).

These translate internal DTOs to wire models; they are pure and trivially
testable.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from graph.nodes import builders as B
from models.schemas_common import InstrumentType, OptionType, WolframEngine
from models.schemas_portfolio import PortfolioPosition
from services.wolfram.dto import (
    ComputeSource,
    GreeksValues,
    WolframEvaluation,
)
from conftest import build_spy_chain


def _wolfram_eval(source: ComputeSource) -> WolframEvaluation:
    if source is ComputeSource.WOLFRAM:
        return WolframEvaluation(
            operation="contract_greeks",
            source=source,
            wl_input="N[D[bs,S]]",
            wl_output="0.52",
            result=0.52,
            kernel_ms=12.0,
        )
    return WolframEvaluation(
        operation="contract_greeks",
        source=source,
        wl_input="N[D[bs,S]]",
        wl_output=None,
        result=0.52,
        fallback_reason="kernel_unavailable",
    )


def test_evaluation_to_computation_wolfram() -> None:
    comp = B.evaluation_to_computation(_wolfram_eval(ComputeSource.WOLFRAM))
    assert comp.engine is WolframEngine.WOLFRAM
    assert comp.evaluated is True
    assert comp.result_raw == "0.52"
    assert comp.fallback_reason is None


def test_evaluation_to_computation_fallback() -> None:
    comp = B.evaluation_to_computation(_wolfram_eval(ComputeSource.NUMERIC_FALLBACK))
    assert comp.engine is WolframEngine.NUMERIC_FALLBACK
    assert comp.evaluated is False
    assert comp.result_raw is None
    assert comp.fallback_reason == "kernel_unavailable"


def test_evaluation_to_computation_overrides() -> None:
    comp = B.evaluation_to_computation(
        _wolfram_eval(ComputeSource.WOLFRAM),
        inputs={"S": 100.0},
        label="Custom",
        result_numeric=0.9,
    )
    assert comp.label == "Custom"
    assert comp.inputs == {"S": 100.0}
    assert comp.result_numeric == 0.9


def test_humanize_operation_known_and_unknown() -> None:
    assert "Contract Greeks" in B.humanize_operation("contract_greeks")
    assert B.humanize_operation("some_op") == "Some Op"


def test_greeks_values_to_wire_scales_theta_and_vega() -> None:
    values = GreeksValues(
        price=10.0, delta=0.5, gamma=0.02, theta=-36.5, vega=10.0, rho=0.1
    )
    wire = B.greeks_values_to_wire(values)
    assert math.isclose(wire.theta, -36.5 / 365.0)
    assert math.isclose(wire.vega, 10.0 * 0.01)
    assert wire.delta == 0.5


def test_years_to_expiry_future_positive() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    yrs = B.years_to_expiry("2027-01-01", now=now)
    assert math.isclose(yrs, 1.0, abs_tol=0.01)


def test_years_to_expiry_past_floors_at_one_day() -> None:
    # A past / 0-DTE expiry is floored to 1 day (1/365 yr) so the Black-Scholes
    # d1 = .../(sig*Sqrt[T]) never divides by zero (see builders._MIN_TTE_DAYS).
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert B.years_to_expiry("2020-01-01", now=now) == 1.0 / 365.0


def test_dte_for_expiry() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert B.dte_for_expiry("2026-01-31", now=now) == 30


def test_wire_position_to_wolfram_option() -> None:
    pos = PortfolioPosition(
        symbol="spy",
        instrument=InstrumentType.CALL,
        strike=530.0,
        expiry="2027-01-15",
        quantity=-5,
    )
    wl_pos = B.wire_position_to_wolfram(pos, spot=530.0, rate=0.05, sigma=0.2)
    assert wl_pos.symbol == "SPY"
    assert wl_pos.signed_qty == -5.0
    assert wl_pos.multiplier == 100.0
    assert wl_pos.cp == 1  # call
    assert wl_pos.t is not None and wl_pos.t > 0.0


def test_wire_position_to_wolfram_equity() -> None:
    pos = PortfolioPosition(
        symbol="SPY", instrument=InstrumentType.EQUITY, quantity=100
    )
    wl_pos = B.wire_position_to_wolfram(pos, spot=530.0)
    assert wl_pos.is_equity is True
    assert wl_pos.multiplier == 1.0
    assert wl_pos.t is None


def test_wire_positions_to_domain_skips_zero() -> None:
    positions = [
        PortfolioPosition(symbol="SPY", instrument=InstrumentType.EQUITY, quantity=0),
        PortfolioPosition(symbol="SPY", instrument=InstrumentType.EQUITY, quantity=10),
    ]
    domain = B.wire_positions_to_domain(positions)
    assert len(domain) == 1


def test_build_iv_stats_from_chain() -> None:
    chain = build_spy_chain()
    stats = B.build_iv_stats(chain)
    assert stats.atm_iv > 0.0
    assert 0.0 <= stats.iv_rank <= 100.0
    assert 0.0 <= stats.iv_percentile <= 100.0


def test_raw_contract_to_quote() -> None:
    chain = build_spy_chain()
    contract = chain.calls[2]  # ATM 530
    from models.schemas_greeks import Greeks

    greeks = Greeks(delta=0.52, gamma=0.02, theta=-0.01, vega=0.1, rho=0.05)
    quote = B.raw_contract_to_quote(
        contract, spot=530.0, ofi=0.1, greeks=greeks, wolfram=None
    )
    assert quote.type is OptionType.CALL
    assert quote.strike == 530.0
    assert quote.delta == 0.52
    assert math.isclose(quote.moneyness, 1.0)


def test_build_market_snapshot() -> None:
    chain = build_spy_chain()
    iv_stats = B.build_iv_stats(chain)
    snapshot = B.build_market_snapshot(
        chain,
        quotes=[],
        iv_stats=iv_stats,
        data_source="fake",
        near_expiry_filter_used="<= 7 dte",
    )
    assert snapshot.symbol == "SPY"
    assert snapshot.calls_count == 5
    assert snapshot.puts_count == 5
    assert -1.0 <= snapshot.order_flow_imbalance <= 1.0
    assert 0.0 <= snapshot.pin_risk_score <= 1.0
