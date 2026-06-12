"""Ops package — background alert re-evaluation (ARCHITECTURE.md §11.3, WS4).

Exposes the APScheduler lifecycle helpers (``start_scheduler`` /
``stop_scheduler``) the integrator calls inside the FastAPI lifespan, and the
sweep entrypoint ``evaluate_all_alerts`` they schedule.
"""

from __future__ import annotations

from ops.alert_evaluator import evaluate_all_alerts
from ops.scheduler import (
    ALERT_SWEEP_INTERVAL_SECONDS,
    ALERT_SWEEP_JOB_ID,
    AlertSchedulerHandle,
    start_scheduler,
    stop_scheduler,
)

__all__ = [
    "evaluate_all_alerts",
    "start_scheduler",
    "stop_scheduler",
    "AlertSchedulerHandle",
    "ALERT_SWEEP_INTERVAL_SECONDS",
    "ALERT_SWEEP_JOB_ID",
]
