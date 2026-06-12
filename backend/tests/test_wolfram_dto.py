"""WolframEvaluation invariant tests (ARCHITECTURE.md §5.5, §5.6).

The frozen DTO enforces the honesty contract structurally: a numeric_fallback
evaluation MUST carry a valid fallback_reason and a null wl_output, and a
wolfram evaluation must NOT carry a fallback_reason.
"""

from __future__ import annotations

import pytest

from services.wolfram.cache import EvaluationCache, LRUCacheBackend, make_cache_key
from services.wolfram.dto import (
    FALLBACK_KERNEL_UNAVAILABLE,
    ComputeSource,
    GreekInputs,
    WolframEvaluation,
)


def _wolfram_eval() -> WolframEvaluation:
    return WolframEvaluation(
        operation="contract_greeks",
        source=ComputeSource.WOLFRAM,
        wl_input="N[1+1]",
        wl_output="2",
        result=2.0,
    )


def _fallback_eval() -> WolframEvaluation:
    return WolframEvaluation(
        operation="contract_greeks",
        source=ComputeSource.NUMERIC_FALLBACK,
        wl_input="N[1+1]",
        wl_output=None,
        result=2.0,
        fallback_reason=FALLBACK_KERNEL_UNAVAILABLE,
    )


def test_wolfram_eval_is_valid() -> None:
    ev = _wolfram_eval()
    assert ev.source is ComputeSource.WOLFRAM
    assert ev.fallback_reason is None


def test_fallback_eval_is_valid() -> None:
    ev = _fallback_eval()
    assert ev.source is ComputeSource.NUMERIC_FALLBACK
    assert ev.wl_output is None


def test_fallback_without_reason_raises() -> None:
    with pytest.raises(ValueError):
        WolframEvaluation(
            operation="x",
            source=ComputeSource.NUMERIC_FALLBACK,
            wl_input="N[1]",
            wl_output=None,
            result=1.0,
            fallback_reason=None,
        )


def test_fallback_with_invalid_reason_raises() -> None:
    with pytest.raises(ValueError):
        WolframEvaluation(
            operation="x",
            source=ComputeSource.NUMERIC_FALLBACK,
            wl_input="N[1]",
            wl_output=None,
            result=1.0,
            fallback_reason="totally_made_up",
        )


def test_fallback_with_wl_output_raises() -> None:
    with pytest.raises(ValueError):
        WolframEvaluation(
            operation="x",
            source=ComputeSource.NUMERIC_FALLBACK,
            wl_input="N[1]",
            wl_output="1",  # fallback must never carry verbatim kernel output
            result=1.0,
            fallback_reason=FALLBACK_KERNEL_UNAVAILABLE,
        )


def test_wolfram_with_fallback_reason_raises() -> None:
    with pytest.raises(ValueError):
        WolframEvaluation(
            operation="x",
            source=ComputeSource.WOLFRAM,
            wl_input="N[1]",
            wl_output="1",
            result=1.0,
            fallback_reason=FALLBACK_KERNEL_UNAVAILABLE,
        )


def test_compute_source_two_values() -> None:
    assert {s.value for s in ComputeSource} == {"wolfram", "numeric_fallback"}


def test_greek_inputs_reject_bad_cp() -> None:
    with pytest.raises(ValueError):
        GreekInputs(spot=100.0, strike=100.0, rate=0.0, sigma=0.2, t=1.0, cp=2)


# ── cache policy ──────────────────────────────────────────────────────────────


def test_cache_only_stores_succeeded() -> None:
    cache = EvaluationCache(LRUCacheBackend(8))
    failed = WolframEvaluation(
        operation="contract_greeks",
        source=ComputeSource.WOLFRAM,
        wl_input="N[1+1]",
        wl_output=None,
        result=None,
        succeeded=False,
    )
    cache.put(failed)
    assert cache.get("contract_greeks", "N[1+1]") is None


def test_cache_hit_flips_cache_hit_flag_only() -> None:
    cache = EvaluationCache(LRUCacheBackend(8))
    ev = _wolfram_eval()
    cache.put(ev)
    hit = cache.get(ev.operation, ev.wl_input)
    assert hit is not None
    assert hit.cache_hit is True
    assert hit.source is ComputeSource.WOLFRAM  # source preserved
    assert hit.wl_output == "2"  # verbatim output preserved


def test_cache_key_namespaced_by_operation() -> None:
    k1 = make_cache_key("contract_greeks", "N[1+1]")
    k2 = make_cache_key("portfolio_greeks", "N[1+1]")
    assert k1 != k2
