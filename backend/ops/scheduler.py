"""APScheduler lifecycle for background alert re-evaluation (§11.3, WS4).

The integrator calls :func:`start_scheduler` inside the FastAPI lifespan after
the shared singletons (``app.state.wolfram`` / ``app.state.market_provider`` /
``app.state.sessionmaker``) are constructed, and :func:`stop_scheduler` on
shutdown. The scheduler runs a single recurring job that drives
:func:`ops.alert_evaluator.evaluate_all_alerts`.

Design constraints (ARCHITECTURE.md §11.3):
  * ``AsyncIOScheduler`` (runs the async coroutine on the app's event loop),
  * ``max_instances=1`` — a slow sweep never overlaps itself,
  * ``coalesce=True`` — missed runs collapse into one,
  * ``jitter=15`` — spread load so sweeps don't align to a hard tick.

The scheduler owns its OWN unit of work: each sweep opens a session from the
injected sessionmaker and commits/rolls back itself (it is NOT request-scoped,
so the request ``get_session`` dependency does not apply — §9.3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ops.alert_evaluator import AlertSweepContext, evaluate_all_alerts

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)

# Sweep cadence + identity (named constants — no magic numbers at call sites).
ALERT_SWEEP_INTERVAL_SECONDS = 60
ALERT_SWEEP_JOB_ID = "alert_sweep"
# §11.3: AsyncIOScheduler(max_instances=1, coalesce=True, jitter=15).
_MAX_INSTANCES = 1
_COALESCE = True
_JITTER_SECONDS = 15


@dataclass
class AlertSchedulerHandle:
    """Opaque handle returned by :func:`start_scheduler`.

    Held by the integrator (e.g. on ``app.state``) so the matching
    :func:`stop_scheduler` can shut the scheduler down cleanly on lifespan exit.
    """

    scheduler: AsyncIOScheduler
    context: AlertSweepContext


async def _run_sweep(context: AlertSweepContext) -> None:
    """Job target: run one full alert sweep, never raising into the scheduler.

    APScheduler logs job exceptions, but we additionally guard here so a single
    failed sweep can never poison the scheduler thread or mask the root cause.
    """
    try:
        await evaluate_all_alerts(context)
    except Exception:  # noqa: BLE001 - a sweep must never crash the scheduler
        logger.exception("Alert sweep raised; scheduler continues")


def start_scheduler(
    *,
    sessionmaker: "async_sessionmaker[AsyncSession]",
    wolfram: object,
    market_provider: object,
    interval_seconds: int = ALERT_SWEEP_INTERVAL_SECONDS,
) -> AlertSchedulerHandle:
    """Construct, configure, and start the alert-sweep scheduler.

    Args:
        sessionmaker: the process-wide async session factory (WS3
            ``get_sessionmaker()``); each sweep opens its own unit of work.
        wolfram: the shared ``WolframService`` singleton (honest engine_mode).
        market_provider: the shared market-data provider singleton.
        interval_seconds: sweep cadence; defaults to
            :data:`ALERT_SWEEP_INTERVAL_SECONDS`.

    Returns:
        An :class:`AlertSchedulerHandle` the caller stores and later passes to
        :func:`stop_scheduler`.
    """
    context = AlertSweepContext(
        sessionmaker=sessionmaker,
        wolfram=wolfram,
        market_provider=market_provider,
    )

    scheduler = AsyncIOScheduler(
        job_defaults={
            "max_instances": _MAX_INSTANCES,
            "coalesce": _COALESCE,
            "misfire_grace_time": interval_seconds,
        }
    )
    scheduler.add_job(
        _run_sweep,
        trigger="interval",
        seconds=interval_seconds,
        jitter=_JITTER_SECONDS,
        id=ALERT_SWEEP_JOB_ID,
        replace_existing=True,
        kwargs={"context": context},
    )
    scheduler.start()
    logger.info(
        "Alert scheduler started",
        extra={
            "job_id": ALERT_SWEEP_JOB_ID,
            "interval_seconds": interval_seconds,
            "jitter_seconds": _JITTER_SECONDS,
            "max_instances": _MAX_INSTANCES,
            "coalesce": _COALESCE,
        },
    )
    return AlertSchedulerHandle(scheduler=scheduler, context=context)


def stop_scheduler(handle: AlertSchedulerHandle | None) -> None:
    """Shut the scheduler down (no-op when ``handle`` is ``None``).

    Called from the lifespan ``finally`` block. ``wait=False`` lets shutdown
    proceed without blocking on an in-flight sweep; the sweep itself owns and
    closes its session.
    """
    if handle is None:
        return
    try:
        handle.scheduler.shutdown(wait=False)
        logger.info("Alert scheduler stopped", extra={"job_id": ALERT_SWEEP_JOB_ID})
    except Exception:  # noqa: BLE001 - shutdown must never crash the lifespan
        logger.exception("Alert scheduler shutdown raised; ignoring on exit")
