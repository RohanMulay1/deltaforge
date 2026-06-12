"""Canonical Pydantic model tests (ARCHITECTURE.md §4).

Covers: JSON round-trip of every wire model, ``extra="forbid"`` rejection, the
two-value engine enum, and the snake_case wire contract (§1 rule 1/2).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from models.schemas_analyze import AnalyzeResponse
from models.schemas_common import (
    InstrumentType,
    OptionType,
    PipelineStage,
    WolframEngine,
)
from models.schemas_greeks import Greeks
from models.schemas_hedge import HedgeRecommendation
from models.schemas_market import IVStats, MarketSnapshot, OptionQuote
from models.schemas_portfolio import (
    Portfolio,
    PortfolioGreeks,
    PortfolioPosition,
)
from models.schemas_requests import AnalyzeRequest, CsvImportRequest
from models.schemas_scenario import ScenarioAxis, ScenarioSurface
from models.schemas_wolfram import EngineStatus, WolframComputation


def _now() -> datetime:
    return datetime(2026, 6, 12, tzinfo=timezone.utc)


def _greeks() -> Greeks:
    return Greeks(delta=0.52, gamma=0.0216, theta=-0.03, vega=0.11, rho=0.05)


def _wolfram() -> WolframComputation:
    return WolframComputation(
        label="Contract Greeks",
        expression="N[D[bs, S]]",
        engine=WolframEngine.WOLFRAM,
        inputs={"S": 530.0, "K": 530.0},
        result_raw="0.52",
        result_numeric=0.52,
        evaluated=True,
        duration_ms=12.3,
        evaluated_at=_now(),
    )


def _option_quote() -> OptionQuote:
    return OptionQuote(
        strike=530.0,
        type=OptionType.CALL,
        expiry="2027-01-15",
        bid=10.4,
        ask=10.7,
        last_price=10.55,
        volume=5400,
        open_interest=15300,
        iv=0.181,
        ofi=0.12,
        greeks=_greeks(),
        delta=0.52,
        moneyness=1.0,
        wolfram=_wolfram(),
    )


def _iv_stats() -> IVStats:
    return IVStats(
        iv_rank=42.0,
        iv_percentile=55.0,
        atm_iv=0.181,
        iv_30d_high=0.221,
        iv_30d_low=0.181,
        term_structure=[("2027-01-15", 0.181)],
    )


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="SPY",
        spot_price=530.0,
        timestamp=_now(),
        expiry_used="2027-01-15",
        near_expiry_filter_used="<= 7 dte",
        dte=217,
        order_flow_imbalance=0.1,
        pin_risk_score=0.4,
        max_pain_strike=530.0,
        iv_stats=_iv_stats(),
        calls_count=5,
        puts_count=5,
        chain=[_option_quote()],
        data_source="fake",
    )


def _portfolio_greeks() -> PortfolioGreeks:
    return PortfolioGreeks(
        delta=250.0,
        gamma=10.8,
        theta=-15.0,
        vega=55.0,
        rho=25.0,
        net_delta_dollars=132500.0,
        per_position={"p1": _greeks()},
    )


def _hedge() -> HedgeRecommendation:
    return HedgeRecommendation(
        symbol="SPY",
        delta_neutral_ratio=-1.0,
        contracts_to_trade=-5,
        option_type_to_trade=OptionType.CALL,
        strike_to_trade=530.0,
        expiry_to_trade="2027-01-15",
        expected_pnl_range=(-100.0, 100.0),
        current_portfolio_delta=250.0,
        residual_delta_after_hedge=0.0,
        delta_target=0.0,
        wolfram_computation_used="NMinimize[...]",
        wolfram=_wolfram(),
        reasoning="neutralize",
    )


def _scenario() -> ScenarioSurface:
    return ScenarioSurface(
        x_axis=ScenarioAxis(name="spot_pct", values=[-10.0, 0.0, 10.0]),
        y_axis=ScenarioAxis(name="iv_pct", values=[-5.0, 0.0, 5.0]),
        pnl_grid=[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]],
        base_pnl=0.0,
        breakeven_spot=525.0,
        wolfram=_wolfram(),
        is_stub=False,
    )


def _engine_status() -> EngineStatus:
    return EngineStatus(
        wolfram_available=True,
        engine_in_use=WolframEngine.WOLFRAM,
        pool_size=2,
        healthy_sessions=2,
        last_probe_ms=5.0,
        note="live",
        last_checked=_now(),
    )


def _analyze_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        symbol="SPY",
        spot_price=530.0,
        expiry="2027-01-15",
        calls_count=5,
        puts_count=5,
        order_flow_imbalance=0.1,
        pin_risk_score=0.4,
        iv_rank=42.0,
        market=_market(),
        options_chain=[_option_quote()],
        portfolio_greeks=_portfolio_greeks(),
        hedge=_hedge(),
        scenario=_scenario(),
        risk_summary="ok",
        wolfram_computation_used="...",
        wolfram_computations=[_wolfram()],
        engine_status=_engine_status(),
        generated_at=_now(),
    )


# ── Round-trip ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "model",
    [
        _greeks(),
        _wolfram(),
        _option_quote(),
        _iv_stats(),
        _market(),
        _portfolio_greeks(),
        _hedge(),
        _scenario(),
        _engine_status(),
        _analyze_response(),
    ],
)
def test_models_round_trip_json(model) -> None:  # type: ignore[no-untyped-def]
    """Every wire model serializes to JSON and parses back identically."""
    dumped = model.model_dump_json()
    restored = type(model).model_validate_json(dumped)
    assert restored == model


def test_analyze_response_keys_are_snake_case() -> None:
    """The wire payload uses snake_case keys end-to-end (§1 rule 1)."""
    data = _analyze_response().model_dump(mode="json")
    for key in ("spot_price", "order_flow_imbalance", "pin_risk_score", "iv_rank"):
        assert key in data
    # No camelCase leaked through.
    assert not any(any(c.isupper() for c in k) for k in data)


# ── extra="forbid" ────────────────────────────────────────────────────────────


def test_greeks_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Greeks(delta=1.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0, unexpected=1.0)  # type: ignore[call-arg]


def test_analyze_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(symbol="SPY", dte_max=7, surprise=True)  # type: ignore[call-arg]


def test_wolfram_computation_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        WolframComputation(
            label="x",
            expression="y",
            engine=WolframEngine.WOLFRAM,
            evaluated=True,
            evaluated_at=_now(),
            bogus="z",  # type: ignore[call-arg]
        )


# ── enums + request validation ────────────────────────────────────────────────


def test_engine_enum_has_exactly_two_values() -> None:
    assert {e.value for e in WolframEngine} == {"wolfram", "numeric_fallback"}


def test_pipeline_stage_canonical_names() -> None:
    assert {s.value for s in PipelineStage} == {
        "market_data",
        "greeks",
        "iv_surface",
        "portfolio",
        "hedge",
        "scenario",
        "summary",
    }


def test_instrument_type_values() -> None:
    assert {i.value for i in InstrumentType} == {"equity", "call", "put"}


def test_analyze_request_symbol_pattern_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(symbol="123$", dte_max=7)


@pytest.mark.parametrize("dte", [0, 366])
def test_analyze_request_dte_bounds(dte: int) -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(symbol="SPY", dte_max=dte)


def test_csv_import_request_requires_non_empty_csv() -> None:
    with pytest.raises(ValidationError):
        CsvImportRequest(csv="")


def test_portfolio_position_signed_quantity() -> None:
    """A short position carries a negative signed quantity (no `side` on wire)."""
    pos = PortfolioPosition(symbol="SPY", quantity=-5)
    assert pos.quantity == -5
    assert pos.instrument is InstrumentType.CALL  # default


def test_portfolio_round_trip() -> None:
    portfolio = Portfolio(
        id="pf1",
        name="Test",
        positions=[PortfolioPosition(symbol="SPY", quantity=10)],
        created_at=_now(),
        updated_at=_now(),
    )
    restored = Portfolio.model_validate_json(portfolio.model_dump_json())
    assert restored == portfolio
