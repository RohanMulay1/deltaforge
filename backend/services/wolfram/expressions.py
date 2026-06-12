"""Pure Wolfram Language expression builders (ARCHITECTURE.md §5.4).

These functions are PURE: given numeric inputs they return WL strings, with no
I/O, no kernel call, and no side effects. They are independently testable.

Ported from the legacy ``backend/agents/wolfram_risk_agent.py`` (``fd_expr``,
``nm_expr``, combined ``wolfram_computation_used``) and extended with:
  - symbolic ``D[]`` Greeks on the closed-form Black-Scholes price,
  - portfolio aggregate ``Total[bsGreeks @@@ book]``,
  - multi-leg ``NMinimize`` hedge (``vars . hedgeDeltas``, real delta target,
    ``Method -> "DifferentialEvolution"``),
  - the symbolic P&L surface ``pnl[S, sig, T]``.

The numeric values are formatted into the displayed InputForm string here.
The service layer additionally wraps each payload as
``<|"value" -> (expr), "form" -> ToString[(expr), InputForm]|>`` and calls
``evaluate_wrap`` so the verbatim kernel ``InputForm`` is captured.

Bump ``WL_BUILDER_VERSION`` whenever any builder's output changes — the cache
key is namespaced by it, so stale entries cannot survive a builder change.
"""

from __future__ import annotations

from collections.abc import Sequence

# Bump on ANY change to the emitted WL strings (cache-key namespace, §5.7).
# 1.1.0: portfolio aggregate Greeks now differentiate symbolically THEN
#        substitute the row numerics (mirror of contract_greeks); the previous
#        1.0.0 form bound S,K,... to numbers before D[] → all derivative Greeks 0.
WL_BUILDER_VERSION = "1.1.0"

# Precision used when injecting numeric literals into display strings.
_PREC = 8


def _num(x: float) -> str:
    """Format a float as a clean WL numeric literal (no trailing zero noise)."""
    if x != x:  # NaN guard
        raise ValueError("cannot serialize NaN to a WL literal")
    if x in (float("inf"), float("-inf")):
        raise ValueError("cannot serialize infinity to a WL literal")
    # Use repr-like formatting then trim; keep enough precision for round-trip.
    s = f"{x:.{_PREC}g}"
    return s


def _wl_real(x: float) -> str:
    """Format a number ensuring it reads as a Real in WL (has a decimal point)."""
    s = _num(x)
    if "e" in s or "E" in s or "." in s:
        return s
    return s + "."


# ── Closed-form Black-Scholes price (symbolic core) ───────────────────────────

# A reusable WL definition of the closed-form BS price as a function of the
# symbols S, K, r, sig, T, cp (+1 call / -1 put). Greeks are symbolic D[] of it.
_BS_PRICE_BODY = (
    "Module[{d1, d2, nd}, "
    "nd[z_] := CDF[NormalDistribution[0, 1], z]; "
    "d1 = (Log[S/K] + (r + sig^2/2) T)/(sig Sqrt[T]); "
    "d2 = d1 - sig Sqrt[T]; "
    "cp (S nd[cp d1] - K Exp[-r T] nd[cp d2])]"
)


def bs_price_function_definition() -> str:
    """Return the WL ``bsPrice[S,K,r,sig,T,cp]`` definition string."""
    return f"bsPrice[S_, K_, r_, sig_, T_, cp_] := {_BS_PRICE_BODY}"


def _subst_clause(inp_spot: float, strike: float, rate: float,
                  sigma: float, t: float, cp: int) -> str:
    """Build the ``/. {S->.., ...}`` substitution clause for numeric eval."""
    return (
        f"{{S -> {_wl_real(inp_spot)}, K -> {_wl_real(strike)}, "
        f"r -> {_wl_real(rate)}, sig -> {_wl_real(sigma)}, "
        f"T -> {_wl_real(t)}, cp -> {cp}}}"
    )


def build_contract_greeks_expr(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    t: float,
    cp: int,
) -> str:
    """Symbolic ``D[]`` Greeks on the closed-form BS price (§5.4).

    Returns an Association
    ``<|"price"->..,"delta"->D[bs,S],"gamma"->D[bs,{S,2}],"vega"->D[bs,sig],
    "theta"->-D[bs,T],"rho"->D[bs,r]|>`` evaluated at the numeric point.

    Theta is reported per-YEAR (UI divides by 365). Vega is per-unit vol
    (per 1.0 of sigma); the caller scales to per-vol-point if desired.
    """
    if cp not in (1, -1):
        raise ValueError("cp must be +1 (call) or -1 (put)")
    subst = _subst_clause(spot, strike, rate, sigma, t, cp)
    # Substitution MUST be applied INSIDE N[] — otherwise N[] coerces the
    # symbolic template before S,K,... are substituted and the kernel returns
    # an unevaluated association (every Greek then parses to 0.0).
    return (
        "Module[{bs, S, K, r, sig, T, cp}, "
        f"bs = {_BS_PRICE_BODY}; "
        "N[(<|"
        '"price" -> bs, '
        '"delta" -> D[bs, S], '
        '"gamma" -> D[bs, {S, 2}], '
        '"vega" -> D[bs, sig], '
        '"theta" -> -D[bs, T], '
        '"rho" -> D[bs, r]'
        "|>) /. " + subst + "]]"
    )


# ── Legacy FinancialDerivative builder (ported verbatim in spirit) ────────────


def build_financial_derivative_expr(
    spot: float,
    strike: float,
    rate: float,
    sigma: float,
    t: float,
    option_type: str,
) -> str:
    """Legacy ``FinancialDerivative`` display string (ported from the old agent).

    Retained so the UI's legacy ``wolfram_computation_used`` text still renders.
    Example::

        FinancialDerivative[{"European","Call"}, {530.5, 535.0, 0.053, 0.18, 0.0137}]
    """
    wl_type = "Call" if option_type == "call" else "Put"
    return (
        f'FinancialDerivative[{{"European","{wl_type}"}}, '
        f"{{{_wl_real(spot)}, {_wl_real(strike)}, {_wl_real(rate)}, "
        f"{_wl_real(sigma)}, {_wl_real(t)}}}]"
    )


# ── Portfolio aggregate Greeks: Total[bsGreeks @@@ book] ──────────────────────


def build_portfolio_greeks_expr(book: Sequence[Sequence[float]]) -> str:
    """Aggregate portfolio Greeks via ``Total[bsGreeks @@@ book]`` (§5.4).

    ``book`` is a matrix where each row is
    ``{qtyMult, S, K, r, sig, T, cp}``; ``qtyMult`` is signed quantity ×
    multiplier. The kernel computes per-leg Greeks symbolically and sums them,
    so the aggregate is itself kernel-verified.

    Equity legs are represented with ``cp == 0`` and contribute ``delta -> 1``,
    everything else ``0`` (handled inside ``bsGreeks``).
    """
    rows = ", ".join(
        "{"
        + ", ".join(
            _wl_real(v) if i != 6 else str(int(v))
            for i, v in enumerate(row)
        )
        + "}"
        for row in book
    )
    book_literal = f"{{{rows}}}"
    # bsGreeks takes the row's NUMERIC values as distinct parameters
    # (qN, sN, kN, rN, sigN, tN, cpN) while the differentiation variables
    # S, K, r, sig, T remain LOCAL SYMBOLS that are kept symbolic for D[],
    # then substituted with the numerics INSIDE N[] — exactly mirroring
    # build_contract_greeks_expr. The previous form bound S,K,... directly
    # to numbers via @@@, so D[bs, S] differentiated w.r.t. a number → 0.
    return (
        "Module[{bsGreeks, book, perLeg}, "
        "bsGreeks[qN_, sN_, kN_, rN_, sigN_, tN_, cpN_] := "
        "Module[{S, K, r, sig, T, bs, g}, "
        "If[cpN === 0, "
        '  <|"delta" -> qN*1., "gamma" -> 0., "vega" -> 0., '
        '    "theta" -> 0., "rho" -> 0.|>, '
        f"  bs = ({_BS_PRICE_BODY}) /. cp -> cpN; "
        '  g = <|"delta" -> D[bs, S], "gamma" -> D[bs, {S, 2}], '
        '        "vega" -> D[bs, sig], "theta" -> -D[bs, T], '
        '        "rho" -> D[bs, r]|>; '
        "  qN * N[g /. {S -> sN, K -> kN, r -> rN, sig -> sigN, T -> tN}]]]; "
        f"book = {book_literal}; "
        "perLeg = bsGreeks @@@ book; "
        "N[Total[perLeg]]]"
    )


# ── Multi-leg delta-neutral hedge: NMinimize / DifferentialEvolution ──────────


def build_hedge_nminimize_expr(
    current_delta: float,
    hedge_deltas: Sequence[float],
    delta_target: float,
    lambda_penalty: float,
    per_leg_caps: Sequence[float],
    gross_cap: float,
) -> str:
    """Multi-leg ``NMinimize`` hedge optimization (§5.4).

    Minimizes::

        (currentDelta + vars . hedgeDeltas - deltaTarget)^2
            + lambda * Total[Abs[vars]]

    subject to per-leg caps ``-cap_i <= v_i <= cap_i`` and a gross cap
    ``Total[Abs[vars]] <= grossCap``, solved with
    ``Method -> "DifferentialEvolution"``.

    Returns ``{objVal, {v1 -> .., v2 -> ..}}`` from ``NMinimize``.
    """
    n = len(hedge_deltas)
    if n == 0:
        # Degenerate: nothing to trade, residual is the unhedgeable delta.
        return (
            'NMinimize[{(' + _wl_real(current_delta) + " - "
            + _wl_real(delta_target) + ")^2, True}, {}, "
            'Method -> "DifferentialEvolution"]'
        )
    if len(per_leg_caps) != n:
        raise ValueError("per_leg_caps length must match hedge_deltas length")

    vars_list = [f"v{i}" for i in range(n)]
    vars_clause = "{" + ", ".join(vars_list) + "}"
    deltas_clause = "{" + ", ".join(_wl_real(d) for d in hedge_deltas) + "}"

    dot = " + ".join(f"v{i} * {_wl_real(hedge_deltas[i])}" for i in range(n))
    abs_sum = " + ".join(f"Abs[v{i}]" for i in range(n))

    leg_constraints = ", ".join(
        f"-{_wl_real(per_leg_caps[i])} <= v{i} <= {_wl_real(per_leg_caps[i])}"
        for i in range(n)
    )
    gross_constraint = f"({abs_sum}) <= {_wl_real(gross_cap)}"
    constraints = f"{leg_constraints}, {gross_constraint}"

    objective = (
        f"(({_wl_real(current_delta)} + ({dot}) - {_wl_real(delta_target)})^2 "
        f"+ {_wl_real(lambda_penalty)} * ({abs_sum}))"
    )

    # deltas_clause kept in the expression for reproducibility/readability.
    return (
        "NMinimize[{"
        f"{objective}, {constraints}"
        "}, "
        f"{vars_clause}, "
        'Method -> "DifferentialEvolution"]'
        f"  (* hedgeDeltas = {deltas_clause} *)"
    )


# ── Symbolic P&L surface: pnl[S, sig, T] over a Table grid ────────────────────


def build_pnl_surface_expr(
    legs: Sequence[Sequence[float]],
    base_spot: float,
    base_rate: float,
    spot_mults: Sequence[float],
    iv_shifts: Sequence[float],
    base_t: float,
) -> str:
    """Symbolic P&L surface (§5.4).

    Defines ``portfolioValue[S, sigShift, T]`` = sum over legs of
    ``qtyMult * bsPrice[S, K, r, sig0_i + sigShift, T, cp_i]`` (equity legs
    use ``qtyMult * S``), then ``pnl[...] = portfolioValue[...] - baseValue``
    evaluated over the ``Table`` grid (spot × IV).

    Each leg row is ``{qtyMult, K, sig0, cp}``. ``cp == 0`` denotes equity.
    Returns ``<|"base" -> baseValue, "grid" -> Table[...]|>`` where ``grid`` is
    indexed ``[ivShift][spotMult]`` matching §4.8's ``[y][x]`` convention.
    """
    leg_rows = ", ".join(
        "{"
        + ", ".join(
            _wl_real(v) if i != 3 else str(int(v))
            for i, v in enumerate(row)
        )
        + "}"
        for row in legs
    )
    legs_literal = f"{{{leg_rows}}}"
    spot_list = "{" + ", ".join(_wl_real(m) for m in spot_mults) + "}"
    iv_list = "{" + ", ".join(_wl_real(s) for s in iv_shifts) + "}"

    return (
        "Module[{bsPrice, legs, legValue, portfolioValue, baseValue, "
        "spotMults, ivShifts, baseS, r, baseT, grid}, "
        f"bsPrice[S_, K_, r0_, sig_, T_, cp_] := "
        + _BS_PRICE_BODY.replace("r ", "r0 ").replace("r T", "r0 T")
        + "; "
        f"legs = {legs_literal}; "
        f"baseS = {_wl_real(base_spot)}; r = {_wl_real(base_rate)}; "
        f"baseT = {_wl_real(base_t)}; "
        f"spotMults = {spot_list}; ivShifts = {iv_list}; "
        "legValue[{q_, K_, sig0_, cp_}, S_, sigShift_, T_] := "
        "If[cp === 0, q * S, q * bsPrice[S, K, r, sig0 + sigShift, T, cp]]; "
        "portfolioValue[S_, sigShift_, T_] := "
        "Total[legValue[#, S, sigShift, T] & /@ legs]; "
        "baseValue = portfolioValue[baseS, 0., baseT]; "
        "grid = Table["
        "portfolioValue[baseS (1 + sm), iv, baseT] - baseValue, "
        "{iv, ivShifts}, {sm, spotMults}]; "
        'N[<|"base" -> baseValue, "grid" -> grid|>]]'
    )


# ── Combined legacy display string (ported) ───────────────────────────────────


def build_combined_legacy_wl(fd_expr: str, nm_expr: str) -> str:
    """Reproduce the legacy combined ``wolfram_computation_used`` string."""
    return (
        "(* Step 1: price and Greeks *)\n"
        f"{fd_expr}\n\n"
        "(* Step 2: delta-neutral hedge optimization *)\n"
        f"{nm_expr}"
    )


# ── Health canary ─────────────────────────────────────────────────────────────


def build_canary_expr() -> str:
    """The live health canary: ``1 + 1`` (expected ``2``)."""
    return "1 + 1"
