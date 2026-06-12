"""Alert predicate + helper tests (ARCHITECTURE.md §11.3, WS4).

Targets the pure ``_check``-style logic: ``_evaluate_predicate``, ``_in_cooldown``,
and ``_resolve_engine_mode``. The DB sweep itself needs a live session and is
out of scope for unit coverage (it is exercised in integration/e2e), but the
predicate logic is the high-value, deterministic core.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ops import alert_evaluator as ae
from models.schemas_common import WolframEngine


def _analysis(
    *,
    delta: float = 0.0,
    gamma: float = 0.0,
    pin: float = 0.0,
    dte: int = 5,
    engine: WolframEngine = WolframEngine.WOLFRAM,
    comps_engine: WolframEngine | None = None,
) -> SimpleNamespace:
    """A duck-typed stand-in for ``AnalyzeResponse`` (only the read fields)."""
    comp_engine = comps_engine if comps_engine is not None else engine
    return SimpleNamespace(
        portfolio_greeks=SimpleNamespace(delta=delta, gamma=gamma),
        pin_risk_score=pin,
        market=SimpleNamespace(dte=dte),
        engine_status=SimpleNamespace(engine_in_use=engine),
        wolfram_computations=[SimpleNamespace(engine=comp_engine)],
    )


def _alert(
    *,
    kind: str,
    threshold: float,
    tolerance: float | None = None,
    dte_window: int | None = None,
    cooldown_seconds: int = 3600,
    last_triggered_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        kind=kind,
        threshold=threshold,
        tolerance=tolerance,
        dte_window=dte_window,
        cooldown_seconds=cooldown_seconds,
        last_triggered_at=last_triggered_at,
    )


# ── delta_drift ───────────────────────────────────────────────────────────────


def test_delta_drift_fires_when_beyond_tolerance() -> None:
    alert = _alert(kind="delta_drift", threshold=0.0, tolerance=10.0)
    analysis = _analysis(delta=25.0)
    fired, observed, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is True
    assert observed == 25.0


def test_delta_drift_quiet_within_tolerance() -> None:
    alert = _alert(kind="delta_drift", threshold=0.0, tolerance=30.0)
    analysis = _analysis(delta=25.0)
    fired, _, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is False


def test_delta_drift_default_tolerance_zero() -> None:
    alert = _alert(kind="delta_drift", threshold=10.0, tolerance=None)
    analysis = _analysis(delta=10.5)
    fired, _, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is True  # any drift > 0 fires with tolerance 0


# ── pin_risk ──────────────────────────────────────────────────────────────────


def test_pin_risk_fires_when_score_and_window_met() -> None:
    alert = _alert(kind="pin_risk", threshold=0.6, dte_window=7)
    analysis = _analysis(pin=0.75, dte=5)
    fired, observed, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is True
    assert observed == 0.75


def test_pin_risk_quiet_when_outside_dte_window() -> None:
    alert = _alert(kind="pin_risk", threshold=0.6, dte_window=3)
    analysis = _analysis(pin=0.9, dte=10)  # dte beyond window
    fired, _, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is False


def test_pin_risk_quiet_below_threshold() -> None:
    alert = _alert(kind="pin_risk", threshold=0.8, dte_window=30)
    analysis = _analysis(pin=0.5, dte=5)
    fired, _, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is False


def test_pin_risk_no_window_means_unbounded() -> None:
    alert = _alert(kind="pin_risk", threshold=0.5, dte_window=None)
    analysis = _analysis(pin=0.6, dte=400)
    fired, _, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is True


# ── gamma_spike ───────────────────────────────────────────────────────────────


def test_gamma_spike_fires_on_magnitude() -> None:
    alert = _alert(kind="gamma_spike", threshold=5.0)
    analysis = _analysis(gamma=-8.0)  # magnitude 8 >= 5
    fired, observed, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is True
    assert observed == -8.0


def test_gamma_spike_quiet_below_threshold() -> None:
    alert = _alert(kind="gamma_spike", threshold=10.0)
    analysis = _analysis(gamma=3.0)
    fired, _, _ = ae._evaluate_predicate(alert, analysis)
    assert fired is False


def test_unknown_kind_never_fires() -> None:
    alert = _alert(kind="mystery", threshold=1.0)
    fired, _, _ = ae._evaluate_predicate(alert, _analysis())
    assert fired is False


# ── cooldown ──────────────────────────────────────────────────────────────────


def test_in_cooldown_true_within_window() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    alert = _alert(
        kind="gamma_spike",
        threshold=1.0,
        cooldown_seconds=3600,
        last_triggered_at=now - timedelta(seconds=600),
    )
    assert ae._in_cooldown(alert, now) is True


def test_in_cooldown_false_after_window() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    alert = _alert(
        kind="gamma_spike",
        threshold=1.0,
        cooldown_seconds=300,
        last_triggered_at=now - timedelta(seconds=600),
    )
    assert ae._in_cooldown(alert, now) is False


def test_in_cooldown_false_when_never_triggered() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    alert = _alert(kind="gamma_spike", threshold=1.0, last_triggered_at=None)
    assert ae._in_cooldown(alert, now) is False


def test_in_cooldown_handles_naive_last_triggered() -> None:
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 6, 12, 11, 59)  # tz-naive
    alert = _alert(
        kind="gamma_spike",
        threshold=1.0,
        cooldown_seconds=3600,
        last_triggered_at=naive,
    )
    assert ae._in_cooldown(alert, now) is True


# ── honest engine_mode resolution ─────────────────────────────────────────────


def test_resolve_engine_mode_wolfram_when_all_wolfram() -> None:
    analysis = _analysis(engine=WolframEngine.WOLFRAM, comps_engine=WolframEngine.WOLFRAM)
    assert ae._resolve_engine_mode(analysis) == "wolfram"


def test_resolve_engine_mode_fallback_when_status_fallback() -> None:
    analysis = _analysis(engine=WolframEngine.NUMERIC_FALLBACK)
    assert ae._resolve_engine_mode(analysis) == "numeric_fallback"


def test_resolve_engine_mode_fallback_when_any_comp_degraded() -> None:
    # status says wolfram, but one computation degraded → honest fallback label.
    analysis = _analysis(
        engine=WolframEngine.WOLFRAM,
        comps_engine=WolframEngine.NUMERIC_FALLBACK,
    )
    assert ae._resolve_engine_mode(analysis) == "numeric_fallback"
