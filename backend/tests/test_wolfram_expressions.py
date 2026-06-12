"""Pure WL expression-builder tests (ARCHITECTURE.md §5.4).

These assert the SHAPE of the emitted Wolfram Language strings — the builders
are pure, so no kernel is involved.
"""

from __future__ import annotations

import pytest

from services.wolfram import expressions as wl


def test_contract_greeks_expr_has_all_greeks() -> None:
    expr = wl.build_contract_greeks_expr(100.0, 100.0, 0.05, 0.2, 1.0, 1)
    for token in ('"price"', '"delta"', '"gamma"', '"vega"', '"theta"', '"rho"'):
        assert token in expr
    # Differentiation operators present.
    assert "D[bs, S]" in expr
    assert "D[bs, {S, 2}]" in expr


def test_contract_greeks_substitution_inside_N() -> None:
    """The substitution MUST be applied inside N[] (the §OPEN-BUG fix)."""
    expr = wl.build_contract_greeks_expr(100.0, 95.0, 0.05, 0.2, 0.5, -1)
    # The structure is N[(<|...|>) /. {S -> ...}] — substitution after the assoc,
    # inside N[]. Assert the assoc is followed by a replacement clause.
    assert "/. {S ->" in expr
    assert expr.strip().endswith("]]")


def test_contract_greeks_rejects_bad_cp() -> None:
    with pytest.raises(ValueError):
        wl.build_contract_greeks_expr(100.0, 100.0, 0.05, 0.2, 1.0, 0)


def test_portfolio_greeks_expr_uses_apply_and_total() -> None:
    book = [[5.0 * 100, 100.0, 100.0, 0.05, 0.2, 1.0, 1]]
    expr = wl.build_portfolio_greeks_expr(book)
    assert "bsGreeks @@@ book" in expr
    assert "Total[perLeg]" in expr
    # cp is an integer literal in the book (index 6).
    assert expr.rstrip().endswith("]")


def test_portfolio_greeks_equity_uses_cp_zero() -> None:
    book = [[100.0, 100.0, 0.0, 0.05, 0.0, 0.0, 0]]  # equity row, cp=0
    expr = wl.build_portfolio_greeks_expr(book)
    assert "If[cpN === 0" in expr


def test_hedge_nminimize_expr_structure() -> None:
    expr = wl.build_hedge_nminimize_expr(
        current_delta=250.0,
        hedge_deltas=[-0.5, 0.4],
        delta_target=0.0,
        lambda_penalty=1e-3,
        per_leg_caps=[100.0, 100.0],
        gross_cap=1000.0,
    )
    assert expr.startswith("NMinimize[")
    assert 'Method -> "DifferentialEvolution"' in expr
    assert "v0" in expr and "v1" in expr
    assert "Abs[v0]" in expr


def test_hedge_nminimize_caps_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        wl.build_hedge_nminimize_expr(
            current_delta=10.0,
            hedge_deltas=[-0.5, 0.4],
            delta_target=0.0,
            lambda_penalty=1e-3,
            per_leg_caps=[100.0],  # wrong length
            gross_cap=1000.0,
        )


def test_hedge_nminimize_empty_legs_degenerate() -> None:
    expr = wl.build_hedge_nminimize_expr(
        current_delta=10.0,
        hedge_deltas=[],
        delta_target=0.0,
        lambda_penalty=1e-3,
        per_leg_caps=[],
        gross_cap=1000.0,
    )
    assert expr.startswith("NMinimize[")


def test_pnl_surface_expr_returns_base_and_grid() -> None:
    legs = [[1.0 * 100, 100.0, 0.2, 1]]
    expr = wl.build_pnl_surface_expr(
        legs=legs,
        base_spot=100.0,
        base_rate=0.05,
        spot_mults=(-0.1, 0.0, 0.1),
        iv_shifts=(-0.05, 0.0, 0.05),
        base_t=0.5,
    )
    assert '"base"' in expr
    assert '"grid"' in expr
    assert "Table[" in expr


def test_canary_expr_is_one_plus_one() -> None:
    assert wl.build_canary_expr() == "1 + 1"


def test_financial_derivative_legacy_string() -> None:
    expr = wl.build_financial_derivative_expr(530.5, 535.0, 0.053, 0.18, 0.0137, "call")
    assert expr.startswith('FinancialDerivative[{"European","Call"}')


def test_num_rejects_nan_and_inf() -> None:
    with pytest.raises(ValueError):
        wl._num(float("nan"))
    with pytest.raises(ValueError):
        wl._num(float("inf"))


def test_wl_real_has_decimal_point() -> None:
    assert "." in wl._wl_real(5.0)


def test_builder_version_present() -> None:
    assert wl.WL_BUILDER_VERSION
