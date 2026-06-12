"""WolframService orchestration — the labeled numeric-fallback path.

Uses ``fake_wolfram`` (wolfram_enabled=False + a dead pool), so every public
method must degrade to a ``numeric_fallback`` result that still carries the WL
expression it *would* have run, and never mislabels itself as ``wolfram``.
"""

from __future__ import annotations

from services.wolfram.dto import (
    ComputeSource,
    GreekInputs,
    HedgeLeg,
    HedgeRequest,
    PnLSurfaceInputs,
    Position,
)


async def test_contract_greeks_falls_back(fake_wolfram) -> None:  # type: ignore[no-untyped-def]
    await fake_wolfram.start()
    res = await fake_wolfram.contract_greeks(
        GreekInputs(spot=725.0, strike=725.0, rate=0.053, sigma=0.18, t=0.02, cp=1)
    )
    ev = res.evaluation
    assert ev.source is ComputeSource.NUMERIC_FALLBACK
    assert ev.fallback_reason  # non-null per the DTO invariant
    assert ev.wl_output is None
    assert ev.wl_input  # the expression that WOULD have run is still emitted
    # ATM call delta ~0.5; gamma strictly positive — the numeric mirror is real math.
    assert 0.4 < res.greeks.delta < 0.62
    assert res.greeks.gamma > 0.0
    await fake_wolfram.stop()


async def test_portfolio_greeks_falls_back_and_aggregates(fake_wolfram) -> None:  # type: ignore[no-untyped-def]
    await fake_wolfram.start()
    positions = (
        Position("SPY", "call", 5.0, 100.0, 725.0, strike=725.0, sigma=0.18, t=0.02),
        Position("SPY", "equity", -100.0, 1.0, 725.0),
    )
    res = await fake_wolfram.portfolio_greeks(positions)
    assert res.evaluation.source is ComputeSource.NUMERIC_FALLBACK
    # 5 long ATM calls (~0.5Δ ×100 ×5 = +250) minus 100 shares ⇒ clearly positive net.
    assert res.delta > 50.0
    await fake_wolfram.stop()


async def test_delta_neutral_hedge_falls_back(fake_wolfram) -> None:  # type: ignore[no-untyped-def]
    await fake_wolfram.start()
    req = HedgeRequest(
        symbol="SPY",
        current_delta=-120.0,
        delta_target=0.0,
        legs=(HedgeLeg(label="c725", delta=0.5, option_type="call", strike=725.0, expiry="2027-01-15"),),
        spot=725.0,
    )
    res = await fake_wolfram.delta_neutral_hedge(req)
    assert res.evaluation.source is ComputeSource.NUMERIC_FALLBACK
    assert len(res.hedge_quantities) == 1
    assert res.delta_target == 0.0
    await fake_wolfram.stop()


async def test_pnl_surface_falls_back_with_grid(fake_wolfram) -> None:  # type: ignore[no-untyped-def]
    await fake_wolfram.start()
    req = PnLSurfaceInputs(
        symbol="SPY",
        spot=725.0,
        rate=0.053,
        legs=(Position("SPY", "call", 1.0, 100.0, 725.0, strike=725.0, sigma=0.18, t=0.02),),
        spot_pcts=(-0.1, 0.0, 0.1),
        iv_pcts=(-0.1, 0.0, 0.1),
    )
    res = await fake_wolfram.pnl_surface(req)
    assert res.evaluation.source is ComputeSource.NUMERIC_FALLBACK
    assert len(res.pnl_grid) == 3 and len(res.pnl_grid[0]) == 3
    await fake_wolfram.stop()


async def test_health_reports_unavailable(fake_wolfram) -> None:  # type: ignore[no-untyped-def]
    await fake_wolfram.start()
    status = await fake_wolfram.health()
    assert status.engine_in_use is ComputeSource.NUMERIC_FALLBACK
    assert status.wolfram_available is False
    await fake_wolfram.stop()
