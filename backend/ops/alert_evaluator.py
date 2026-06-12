"""Background alert re-evaluation sweep (ARCHITECTURE.md §11.3, WS4).

``evaluate_all_alerts`` is the scheduled entrypoint. It:

  1. loads every ACTIVE alert via the WS3 ``AlertRepository`` (one query),
  2. GROUPS them BY symbol (no N+1 — the analysis runs ONCE per symbol),
  3. runs the WS2 pipeline ``run_analysis`` once for each symbol,
  4. persists exactly one append-only ``SavedAnalysis`` row per analyzed
     symbol with the HONEST ``engine_mode`` (``wolfram`` vs
     ``numeric_fallback``),
  5. evaluates each alert's predicate, respecting ``cooldown_seconds``,
  6. on a firing, writes an append-only ``AlertEvent`` linked to the real
     ``saved_analyses`` row and stamps ``last_triggered_at``,
  7. always stamps ``last_evaluated_at``.

Isolation guarantee (acceptance §WS4): one symbol's failure must NOT abort the
sweep. Each symbol is processed in its own try/except + its own DB
transaction, so a failure rolls back only that symbol's work.

The sweep owns its OWN unit of work (it is not request-scoped): it opens a
session from the injected sessionmaker and commits/rolls back per symbol.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from db.models.alert import Alert, AlertEvent
from db.models.saved_analysis import SavedAnalysis
from db.repositories.alert_repo import AlertEventRepository, AlertRepository
from db.repositories.analysis_repo import SavedAnalysisRepository
from models.schemas_analyze import AnalyzeResponse
from models.schemas_common import WolframEngine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)

# Canonical engine-mode strings (mirror the SavedAnalysis CHECK constraint).
_ENGINE_WOLFRAM = WolframEngine.WOLFRAM.value
_ENGINE_FALLBACK = WolframEngine.NUMERIC_FALLBACK.value
# A larger dte_max is used for the sweep so pin-risk dte gating has headroom.
_SWEEP_DTE_MAX = 7


@dataclass
class AlertSweepContext:
    """Everything one sweep needs, injected by the scheduler (no globals).

    ``sessionmaker`` yields the unit of work; ``wolfram`` and ``market_provider``
    are the shared singletons the WS2 pipeline consumes. They are typed as
    ``object`` here to avoid importing WS2/WolframService at module load (the
    pipeline is imported lazily inside the sweep).
    """

    sessionmaker: "async_sessionmaker[AsyncSession]"
    wolfram: object
    market_provider: object


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _resolve_engine_mode(analysis: AnalyzeResponse) -> str:
    """Derive the HONEST engine_mode from a completed analysis.

    The label is ``wolfram`` ONLY when the real kernel produced the result:
    the engine status must report ``wolfram`` AND no individual computation may
    have degraded to the numeric fallback. Any fallback ⇒ ``numeric_fallback``
    (never mislabel a numeric result as Wolfram — §5.6).
    """
    status_engine = analysis.engine_status.engine_in_use
    if status_engine != WolframEngine.WOLFRAM:
        return _ENGINE_FALLBACK
    for comp in analysis.wolfram_computations:
        if comp.engine != WolframEngine.WOLFRAM:
            return _ENGINE_FALLBACK
    return _ENGINE_WOLFRAM


def _in_cooldown(alert: Alert, now: datetime) -> bool:
    """True if the alert fired within its ``cooldown_seconds`` window."""
    last = alert.last_triggered_at
    if last is None:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last < timedelta(seconds=alert.cooldown_seconds)


def _evaluate_predicate(
    alert: Alert, analysis: AnalyzeResponse
) -> tuple[bool, float, str]:
    """Evaluate one alert's predicate against the analysis.

    Returns ``(fired, observed_value, message)``. ``observed_value`` is the
    metric that was compared (persisted on the event for auditability).

    Predicates (§WS4):
      * ``delta_drift``  — |portfolio_delta - target| > tolerance
      * ``pin_risk``     — pin_risk_score >= threshold AND dte <= dte_window
      * ``gamma_spike``  — |portfolio_gamma| >= threshold
    """
    kind = alert.kind
    threshold = float(alert.threshold)

    if kind == "delta_drift":
        # target is the alert threshold; tolerance is the allowed drift band.
        target = threshold
        tolerance = float(alert.tolerance) if alert.tolerance is not None else 0.0
        observed = analysis.portfolio_greeks.delta
        drift = abs(observed - target)
        fired = drift > tolerance
        message = (
            f"delta_drift: |Δ {observed:.4f} − target {target:.4f}| = "
            f"{drift:.4f} > tolerance {tolerance:.4f}"
        )
        return fired, observed, message

    if kind == "pin_risk":
        observed = analysis.pin_risk_score
        dte = analysis.market.dte
        dte_window = alert.dte_window
        within_window = dte_window is None or dte <= dte_window
        fired = observed >= threshold and within_window
        message = (
            f"pin_risk: score {observed:.4f} >= threshold {threshold:.4f} "
            f"AND dte {dte} <= window {dte_window}"
        )
        return fired, observed, message

    if kind == "gamma_spike":
        observed = analysis.portfolio_greeks.gamma
        magnitude = abs(observed)
        fired = magnitude >= threshold
        message = (
            f"gamma_spike: |Γ {observed:.4f}| = {magnitude:.4f} "
            f">= threshold {threshold:.4f}"
        )
        return fired, observed, message

    # Defensive: unknown kind never fires (kind is enum-constrained upstream).
    logger.warning("Unknown alert kind; not firing", extra={"kind": kind})
    return False, 0.0, f"unknown alert kind: {kind}"


def _build_saved_analysis(
    symbol: str, analysis: AnalyzeResponse, engine_mode: str
) -> SavedAnalysis:
    """Map an ``AnalyzeResponse`` to an append-only ``SavedAnalysis`` row."""
    return SavedAnalysis(
        symbol=symbol,
        dte_max=_SWEEP_DTE_MAX,
        spot_price=Decimal(str(analysis.spot_price)),
        expiry_used=analysis.expiry,
        order_flow_imbalance=Decimal(str(analysis.order_flow_imbalance)),
        pin_risk_score=Decimal(str(analysis.pin_risk_score)),
        engine_mode=engine_mode,
        wolfram_expressions=[
            comp.model_dump(mode="json") for comp in analysis.wolfram_computations
        ],
        wolfram_computation_used=analysis.wolfram_computation_used,
        portfolio_greeks=analysis.portfolio_greeks.model_dump(mode="json"),
        hedge_recommendation=analysis.hedge.model_dump(mode="json"),
        full_response=analysis.model_dump(mode="json"),
        risk_summary=analysis.risk_summary,
    )


async def _run_pipeline(
    context: AlertSweepContext, symbol: str
) -> AnalyzeResponse:
    """Invoke the WS2 pipeline entrypoint once for a symbol.

    Imported lazily (inside the call) so this module never depends on WS2 at
    import time and the scheduler can be constructed before the pipeline lands.
    The pipeline produces the canonical ``AnalyzeResponse`` (ARCHITECTURE.md §6).
    """
    from graph.pipeline import run_analysis  # WS2 entrypoint

    result = await run_analysis(
        symbol=symbol,
        dte_max=_SWEEP_DTE_MAX,
        market_provider=context.market_provider,
        wolfram=context.wolfram,
    )
    if not isinstance(result, AnalyzeResponse):
        # The pipeline contract is AnalyzeResponse; coerce defensively so a
        # dict-returning variant still validates against the canonical schema.
        result = AnalyzeResponse.model_validate(result)
    return result


def _build_event(
    alert: Alert,
    observed: float,
    message: str,
    saved_analysis: SavedAnalysis,
    now: datetime,
) -> AlertEvent:
    """Construct an append-only ``AlertEvent`` linked to the saved analysis."""
    snapshot: dict[str, Any] = {
        "kind": alert.kind,
        "symbol": alert.symbol,
        "engine_mode": saved_analysis.engine_mode,
    }
    return AlertEvent(
        alert_id=alert.id,
        triggered_at=now,
        observed_value=Decimal(str(observed)),
        threshold_at_trigger=Decimal(str(alert.threshold)),
        message=message,
        snapshot=snapshot,
        saved_analysis_id=saved_analysis.id,
    )


async def _process_symbol(
    session: "AsyncSession",
    context: AlertSweepContext,
    symbol: str,
    alerts: list[Alert],
) -> int:
    """Process all alerts for one symbol; return the count of fired events.

    Runs the analysis once, persists one ``SavedAnalysis``, then checks every
    alert. Each alert that fires (and is not in cooldown) gets an append-only
    ``AlertEvent`` linked to the saved row. ``last_evaluated_at`` is always
    stamped; ``last_triggered_at`` only on a firing.
    """
    analysis = await _run_pipeline(context, symbol)
    engine_mode = _resolve_engine_mode(analysis)

    analysis_repo = SavedAnalysisRepository(session)
    event_repo = AlertEventRepository(session)

    saved = _build_saved_analysis(symbol, analysis, engine_mode)
    await analysis_repo.add(saved)  # flush assigns the PK used by events

    now = _now()
    fired_count = 0

    for alert in alerts:
        alert.last_evaluated_at = now

        if _in_cooldown(alert, now):
            logger.debug(
                "Alert in cooldown; skipping",
                extra={"alert_id": str(alert.id), "symbol": symbol},
            )
            continue

        fired, observed, message = _evaluate_predicate(alert, analysis)
        if not fired:
            continue

        event = _build_event(alert, observed, message, saved, now)
        await event_repo.add(event)
        alert.last_triggered_at = now
        fired_count += 1
        logger.info(
            "Alert fired",
            extra={
                "alert_id": str(alert.id),
                "symbol": symbol,
                "kind": alert.kind,
                "observed": observed,
                "engine_mode": engine_mode,
            },
        )

    return fired_count


async def evaluate_all_alerts(context: AlertSweepContext) -> None:
    """Run one full alert sweep (the scheduled job target).

    Groups active alerts by symbol, runs the pipeline once per symbol, and
    fires events. One symbol's failure is isolated: it rolls back only that
    symbol's transaction and the sweep continues.
    """
    sessionmaker = context.sessionmaker

    # Load active alerts in a short read-only session, then release it before
    # the (potentially slow) per-symbol analysis transactions.
    async with sessionmaker() as session:
        alert_repo = AlertRepository(session)
        active = await alert_repo.list_active()

    if not active:
        logger.debug("Alert sweep: no active alerts")
        return

    by_symbol: dict[str, list[Alert]] = defaultdict(list)
    for alert in active:
        by_symbol[alert.symbol.upper()].append(alert)

    logger.info(
        "Alert sweep starting",
        extra={"alert_count": len(active), "symbol_count": len(by_symbol)},
    )

    total_fired = 0
    for symbol, alerts in by_symbol.items():
        # Re-fetch the alert rows into THIS transaction's session so mutations
        # (last_evaluated_at / last_triggered_at) are tracked and committed.
        try:
            async with sessionmaker() as session:
                repo = AlertRepository(session)
                bound = await repo.list_by_symbol(symbol)
                if not bound:
                    continue
                fired = await _process_symbol(session, context, symbol, bound)
                await session.commit()
                total_fired += fired
        except Exception:  # noqa: BLE001 - isolate one symbol's failure
            logger.exception(
                "Alert sweep failed for symbol; continuing",
                extra={"symbol": symbol},
            )
            continue

    logger.info(
        "Alert sweep complete",
        extra={"symbols_processed": len(by_symbol), "events_fired": total_fired},
    )
