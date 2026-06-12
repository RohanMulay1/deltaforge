"""WolframService fallback + honesty tests (ARCHITECTURE.md §5.6).

The ``fake_wolfram`` fixture forces ``live_mode=False``, so EVERY method here
flows through the labeled numeric fallback. Hard guarantees verified:

  * a fallback evaluation NEVER carries ``source = WOLFRAM``;
  * a non-null, valid ``fallback_reason`` is always present;
  * ``wl_input`` (the expression we *would* run) is still emitted, ``wl_output``
    is ``None``;
  * the fallback math is self-consistent (ATM call delta ≈ 0.5).

A parity test (fallback vs an independent closed-form) confirms the numeric
mirror is faithful.
"""

from __future__ import annotations

import math

import pytest

from services.wolfram.dto import (
    ComputeSource,
    GreekInputs,
    HedgeLeg,
    HedgeRequest,
    PnLSurfaceInputs,
    Position,
    VALID_FALLBACK_REASONS,
)
from services.wolfram.service import WolframService


def _atm_call() -> GreekInputs:
    return GreekInputs(spot=100.0, strike=100.0, rate=0.05, sigma=0.2, t=1.0, cp=1)


async def test_contract_greeks_uses_numeric_fallback(
    fake_wolfram: WolframService,
) -> None:
    result = await fake_wolfram.contract_greeks(_atm_call())
    ev = result.evaluation
    assert ev.source is ComputeSource.NUMERIC_FALLBACK
    assert ev.fallback_reason in VALID_FALLBACK_REASONS
    assert ev.wl_output is None
    assert ev.wl_input  # the expression we would have run is still present


async def test_contract_greeks_never_emits_wolfram(
    fake_wolfram: WolframService,
) -> None:
    result = await fake_wolfram.contract_greeks(_atm_call())
    assert result.evaluation.source is not ComputeSource.WOLFRAM


async def test_atm_call_delta_is_above_half(fake_wolfram: WolframService) -> None:
    # ATM call with positive carry → delta slightly above 0.5.
    result = await fake_wolfram.contract_greeks(_atm_call())
    assert 0.5 < result.greeks.delta < 0.7
    assert result.greeks.gamma > 0.0
    assert result.greeks.price > 0.0


async def test_put_delta_is_negative(fake_wolfram: WolframService) -> None:
    put = GreekInputs(spot=100.0, strike=100.0, rate=0.05, sigma=0.2, t=1.0, cp=-1)
    result = await fake_wolfram.contract_greeks(put)
    assert -1.0 < result.greeks.delta < 0.0


async def test_call_put_parity_delta(fake_wolfram: WolframService) -> None:
    # call_delta - put_delta == 1 for European options on a non-dividend asset.
    call = await fake_wolfram.contract_greeks(_atm_call())
    put = await fake_wolfram.contract_greeks(
        GreekInputs(spot=100.0, strike=100.0, rate=0.05, sigma=0.2, t=1.0, cp=-1)
    )
    assert math.isclose(call.greeks.delta - put.greeks.delta, 1.0, abs_tol=1e-6)


async def test_portfolio_greeks_fallback_aggregates(
    fake_wolfram: WolframService,
) -> None:
    # 5 long ATM calls -> aggregate delta ≈ 5 * 100 * per_unit_delta.
    pos = Position(
        symbol="SPY",
        instrument="call",
        signed_qty=5.0,
        multiplier=100.0,
        spot=100.0,
        strike=100.0,
        rate=0.05,
        sigma=0.2,
        t=1.0,
    )
    result = await fake_wolfram.portfolio_greeks([pos])
    assert result.evaluation.source is ComputeSource.NUMERIC_FALLBACK
    # weight 500, per-unit delta ~0.6 -> aggregate ~300.
    assert result.delta > 250.0


async def test_hedge_fallback_reduces_residual(fake_wolfram: WolframService) -> None:
    req = HedgeRequest(
        symbol="SPY",
        current_delta=250.0,
        delta_target=0.0,
        legs=(
            HedgeLeg(
                label="put 500",
                delta=-0.5,
                option_type="put",
                strike=500.0,
                expiry="2099-12-18",
            ),
        ),
        spot=500.0,
    )
    result = await fake_wolfram.delta_neutral_hedge(req)
    assert result.evaluation.source is ComputeSource.NUMERIC_FALLBACK
    # The optimizer should drive residual toward 0 (|residual| < |current|).
    assert abs(result.residual_delta) < abs(req.current_delta)


async def test_pnl_surface_fallback_grid_shape(fake_wolfram: WolframService) -> None:
    pos = Position(
        symbol="SPY",
        instrument="call",
        signed_qty=1.0,
        multiplier=100.0,
        spot=100.0,
        strike=100.0,
        rate=0.05,
        sigma=0.2,
        t=0.5,
    )
    inputs = PnLSurfaceInputs(
        symbol="SPY",
        spot=100.0,
        rate=0.05,
        legs=(pos,),
        spot_pcts=(-0.1, 0.0, 0.1),
        iv_pcts=(-0.05, 0.0, 0.05),
    )
    result = await fake_wolfram.pnl_surface(inputs)
    assert result.evaluation.source is ComputeSource.NUMERIC_FALLBACK
    assert len(result.pnl_grid) == 3  # y axis (iv)
    assert all(len(row) == 3 for row in result.pnl_grid)  # x axis (spot)


async def test_health_reports_fallback(fake_wolfram: WolframService) -> None:
    status = await fake_wolfram.health()
    assert status.wolfram_available is False
    assert status.engine_in_use is ComputeSource.NUMERIC_FALLBACK
    assert status.reason is not None
    assert status.note


async def test_parity_fallback_matches_independent_closed_form(
    fake_wolfram: WolframService,
) -> None:
    """The numeric fallback agrees with an independent Black-Scholes delta."""
    from scipy.stats import norm

    s, k, r, sig, t = 105.0, 100.0, 0.03, 0.25, 0.75
    result = await fake_wolfram.contract_greeks(
        GreekInputs(spot=s, strike=k, rate=r, sigma=sig, t=t, cp=1)
    )
    d1 = (math.log(s / k) + (r + 0.5 * sig * sig) * t) / (sig * math.sqrt(t))
    expected_delta = float(norm.cdf(d1))
    assert math.isclose(result.greeks.delta, expected_delta, abs_tol=1e-6)
