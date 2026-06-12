"""Numeric fallback mirror of every Wolfram builder (ARCHITECTURE.md §5.6).

This module reproduces each symbolic computation numerically using
numpy / scipy / mpmath closed forms. Hard rules enforced here:

  - Every returned ``WolframEvaluation`` carries
    ``source = ComputeSource.NUMERIC_FALLBACK`` and a NON-NULL
    ``fallback_reason``. (Enforced again in ``WolframEvaluation.__post_init__``.)
  - It NEVER emits ``ComputeSource.WOLFRAM`` — there is no code path that can.
  - It still emits ``wl_input`` (the expression we *would* have run) but
    ``wl_output = None`` (no kernel produced verbatim output).

The math is a faithful mirror so the parity test (both paths agree within
tolerance) passes.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import mpmath
import numpy as np
from scipy.optimize import differential_evolution
from scipy.stats import norm

from services.wolfram import expressions as wl
from services.wolfram.dto import (
    ComputeSource,
    GreeksResult,
    GreeksValues,
    HedgeRequest,
    HedgeResult,
    PnLSurfaceInputs,
    PnLSurfaceResult,
    PortfolioGreeksResult,
    Position,
    WolframEvaluation,
)

logger = logging.getLogger(__name__)

# A tiny floor on time/vol to avoid singular Black-Scholes inputs.
_EPS = 1e-12


# ── Closed-form Black-Scholes (numpy/scipy) ───────────────────────────────────


def _bs_greeks(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    t: float,
    cp: int,
) -> GreeksValues:
    """Closed-form BS price + Greeks. Theta per-YEAR, vega per unit vol.

    Mirrors ``build_contract_greeks_expr`` exactly (same sign conventions).
    """
    if t <= _EPS or sigma <= _EPS or spot <= _EPS or strike <= _EPS:
        intrinsic = max(0.0, cp * (spot - strike))
        delta = float(cp) if intrinsic > 0 else 0.0
        return GreeksValues(
            price=intrinsic, delta=delta, gamma=0.0, theta=0.0, vega=0.0, rho=0.0
        )

    sqrt_t = np.sqrt(t)
    d1 = (np.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    disc = np.exp(-rate * t)
    pdf_d1 = norm.pdf(d1)

    price = cp * (spot * norm.cdf(cp * d1) - strike * disc * norm.cdf(cp * d2))
    delta = cp * norm.cdf(cp * d1)
    gamma = pdf_d1 / (spot * sigma * sqrt_t)
    vega = spot * pdf_d1 * sqrt_t  # per unit sigma (per 1.0 vol)
    # theta = -d(price)/d? -> per-year; matches -D[bs, T] in the WL builder.
    theta = (
        -(spot * pdf_d1 * sigma) / (2.0 * sqrt_t)
        - cp * rate * strike * disc * norm.cdf(cp * d2)
    )
    rho = cp * strike * t * disc * norm.cdf(cp * d2)

    return GreeksValues(
        price=float(price),
        delta=float(delta),
        gamma=float(gamma),
        theta=float(theta),
        vega=float(vega),
        rho=float(rho),
    )


def _bs_price(
    spot: float, strike: float, rate: float, sigma: float, t: float, cp: int
) -> float:
    """Black-Scholes price using mpmath for a high-precision numeric mirror."""
    if t <= _EPS or sigma <= _EPS or spot <= _EPS or strike <= _EPS:
        return float(max(0.0, cp * (spot - strike)))
    s = mpmath.mpf(spot)
    k = mpmath.mpf(strike)
    r = mpmath.mpf(rate)
    sig = mpmath.mpf(sigma)
    tt = mpmath.mpf(t)
    d1 = (mpmath.log(s / k) + (r + sig * sig / 2) * tt) / (sig * mpmath.sqrt(tt))
    d2 = d1 - sig * mpmath.sqrt(tt)
    ncdf = lambda z: mpmath.mpf(0.5) * mpmath.erfc(-z / mpmath.sqrt(2))
    val = cp * (s * ncdf(cp * d1) - k * mpmath.e ** (-r * tt) * ncdf(cp * d2))
    return float(val)


# ── Public fallback builders (each labels source=NUMERIC_FALLBACK) ────────────


def contract_greeks_fallback(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    t: float,
    cp: int,
    fallback_reason: str,
) -> GreeksResult:
    """Numeric mirror of ``contract_greeks``. Always labeled numeric_fallback."""
    greeks = _bs_greeks(spot, strike, rate, sigma, t, cp)
    wl_input = wl.build_contract_greeks_expr(spot, strike, rate, sigma, t, cp)
    evaluation = WolframEvaluation(
        operation="contract_greeks",
        source=ComputeSource.NUMERIC_FALLBACK,
        wl_input=wl_input,
        wl_output=None,
        result={
            "price": greeks.price,
            "delta": greeks.delta,
            "gamma": greeks.gamma,
            "vega": greeks.vega,
            "theta": greeks.theta,
            "rho": greeks.rho,
        },
        succeeded=True,
        fallback_reason=fallback_reason,
    )
    return GreeksResult(greeks=greeks, evaluation=evaluation)


def portfolio_greeks_fallback(
    positions: Sequence[Position],
    fallback_reason: str,
) -> PortfolioGreeksResult:
    """Numeric mirror of ``portfolio_greeks``: Σ qtyMult × per-unit greek."""
    book: list[list[float]] = []
    per_position: dict[str, GreeksValues] = {}
    agg = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

    for idx, pos in enumerate(positions):
        qty_mult = pos.signed_qty * pos.multiplier
        pid = pos.position_id or f"pos_{idx}"
        if pos.is_equity:
            unit = GreeksValues(
                price=pos.spot, delta=1.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0
            )
            book.append([qty_mult, pos.spot, 0.0, pos.rate, 0.0, 0.0, 0])
        else:
            strike = pos.strike if pos.strike is not None else pos.spot
            sigma = pos.sigma if pos.sigma is not None else 0.0
            t = pos.t if pos.t is not None else 0.0
            unit = _bs_greeks(pos.spot, strike, pos.rate, sigma, t, pos.cp)
            book.append([qty_mult, pos.spot, strike, pos.rate, sigma, t, pos.cp])

        # Scaled per-position contribution (matches WL q * greeks).
        scaled = GreeksValues(
            price=unit.price * qty_mult,
            delta=unit.delta * qty_mult,
            gamma=unit.gamma * qty_mult,
            theta=unit.theta * qty_mult,
            vega=unit.vega * qty_mult,
            rho=unit.rho * qty_mult,
        )
        per_position[pid] = scaled
        agg["delta"] += scaled.delta
        agg["gamma"] += scaled.gamma
        agg["vega"] += scaled.vega
        agg["theta"] += scaled.theta
        agg["rho"] += scaled.rho

    wl_input = wl.build_portfolio_greeks_expr(book)
    evaluation = WolframEvaluation(
        operation="portfolio_greeks",
        source=ComputeSource.NUMERIC_FALLBACK,
        wl_input=wl_input,
        wl_output=None,
        result=dict(agg),
        succeeded=True,
        fallback_reason=fallback_reason,
    )
    return PortfolioGreeksResult(
        delta=agg["delta"],
        gamma=agg["gamma"],
        theta=agg["theta"],
        vega=agg["vega"],
        rho=agg["rho"],
        per_position=per_position,
        evaluation=evaluation,
    )


def hedge_fallback(req: HedgeRequest, fallback_reason: str) -> HedgeResult:
    """Numeric mirror of ``delta_neutral_hedge`` via scipy differential_evolution."""
    hedge_deltas = np.array([leg.delta for leg in req.legs], dtype=float)
    per_leg_caps = [leg.max_contracts for leg in req.legs]
    n = len(req.legs)

    wl_input = wl.build_hedge_nminimize_expr(
        current_delta=req.current_delta,
        hedge_deltas=hedge_deltas.tolist(),
        delta_target=req.delta_target,
        lambda_penalty=req.lambda_penalty,
        per_leg_caps=per_leg_caps,
        gross_cap=req.gross_cap,
    )

    if n == 0:
        residual = req.current_delta - req.delta_target
        evaluation = _hedge_eval(wl_input, (), residual, residual * residual,
                                 fallback_reason)
        return HedgeResult(
            hedge_quantities=(),
            residual_delta=residual,
            objective_value=residual * residual,
            delta_target=req.delta_target,
            current_delta=req.current_delta,
            evaluation=evaluation,
        )

    def objective(v: np.ndarray) -> float:
        residual = req.current_delta + float(v @ hedge_deltas) - req.delta_target
        penalty = req.lambda_penalty * float(np.sum(np.abs(v)))
        return residual * residual + penalty

    bounds = [(-cap, cap) for cap in per_leg_caps]
    result = differential_evolution(
        objective,
        bounds,
        seed=0,
        maxiter=200,
        tol=1e-10,
        polish=True,
    )
    v_opt = np.asarray(result.x, dtype=float)

    # Enforce the gross cap by projection if the optimizer drifted past it.
    gross = float(np.sum(np.abs(v_opt)))
    if gross > req.gross_cap and gross > 0:
        v_opt = v_opt * (req.gross_cap / gross)

    residual = req.current_delta + float(v_opt @ hedge_deltas) - req.delta_target
    obj_val = float(objective(v_opt))
    evaluation = _hedge_eval(
        wl_input, tuple(float(x) for x in v_opt), residual, obj_val, fallback_reason
    )
    return HedgeResult(
        hedge_quantities=tuple(float(x) for x in v_opt),
        residual_delta=residual,
        objective_value=obj_val,
        delta_target=req.delta_target,
        current_delta=req.current_delta,
        evaluation=evaluation,
    )


def _hedge_eval(
    wl_input: str,
    quantities: tuple[float, ...],
    residual: float,
    obj_val: float,
    fallback_reason: str,
) -> WolframEvaluation:
    return WolframEvaluation(
        operation="delta_neutral_hedge",
        source=ComputeSource.NUMERIC_FALLBACK,
        wl_input=wl_input,
        wl_output=None,
        result={
            "hedge_quantities": list(quantities),
            "residual_delta": residual,
            "objective_value": obj_val,
        },
        succeeded=True,
        fallback_reason=fallback_reason,
    )


def pnl_surface_fallback(
    inputs: PnLSurfaceInputs,
    fallback_reason: str,
) -> PnLSurfaceResult:
    """Numeric mirror of ``pnl_surface`` via a vectorized numpy grid."""
    base_t = inputs.dte_override if inputs.dte_override is not None else _avg_t(inputs.legs)

    leg_rows: list[list[float]] = []
    for pos in inputs.legs:
        qty_mult = pos.signed_qty * pos.multiplier
        if pos.is_equity:
            leg_rows.append([qty_mult, 0.0, 0.0, 0])
        else:
            strike = pos.strike if pos.strike is not None else pos.spot
            sigma = pos.sigma if pos.sigma is not None else 0.0
            leg_rows.append([qty_mult, strike, sigma, pos.cp])

    wl_input = wl.build_pnl_surface_expr(
        legs=leg_rows,
        base_spot=inputs.spot,
        base_rate=inputs.rate,
        spot_mults=inputs.spot_pcts,
        iv_shifts=inputs.iv_pcts,
        base_t=base_t,
    )

    base_value = _portfolio_value(inputs, leg_rows, inputs.spot, 0.0, base_t)

    grid: list[list[float]] = []
    for iv_shift in inputs.iv_pcts:  # y axis
        row: list[float] = []
        for spot_mult in inputs.spot_pcts:  # x axis
            s = inputs.spot * (1.0 + spot_mult)
            value = _portfolio_value(inputs, leg_rows, s, iv_shift, base_t)
            row.append(value - base_value)
        grid.append(row)

    evaluation = WolframEvaluation(
        operation="pnl_surface",
        source=ComputeSource.NUMERIC_FALLBACK,
        wl_input=wl_input,
        wl_output=None,
        result={"base": base_value, "grid": grid},
        succeeded=True,
        fallback_reason=fallback_reason,
    )
    return PnLSurfaceResult(
        pnl_grid=tuple(tuple(r) for r in grid),
        base_pnl=base_value,
        spot_pcts=tuple(inputs.spot_pcts),
        iv_pcts=tuple(inputs.iv_pcts),
        evaluation=evaluation,
    )


def _avg_t(legs: Sequence[Position]) -> float:
    ts = [p.t for p in legs if (not p.is_equity) and p.t is not None]
    return float(np.mean(ts)) if ts else 0.0


def _portfolio_value(
    inputs: PnLSurfaceInputs,
    leg_rows: Sequence[Sequence[float]],
    spot: float,
    iv_shift: float,
    t: float,
) -> float:
    total = 0.0
    for qty_mult, strike, sig0, cp in leg_rows:
        cp_i = int(cp)
        if cp_i == 0:
            total += qty_mult * spot
        else:
            total += qty_mult * _bs_price(
                spot, strike, inputs.rate, max(sig0 + iv_shift, _EPS), t, cp_i
            )
    return total
