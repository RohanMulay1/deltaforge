"""Alerts router (ARCHITECTURE.md §3, §9, WS4).

Endpoints:
    GET    /alerts          → list[AlertOut]   (optionally filtered by symbol)
    POST   /alerts          → AlertOut         (create, body ``AlertCreate``)
    PATCH  /alerts/{id}      → AlertOut         (partial update: toggle/thresholds)
    DELETE /alerts/{id}      → 204

Alerts are mutable configuration (§9.3): the ``AlertRepository`` supports full
CRUD. Their FIRINGS are the append-only ``alert_events`` rows written by the
background sweep (``ops.alert_evaluator``) — not by this router.

Per-request work uses the ``get_session`` unit of work (commit on clean exit,
rollback on error — §9.3); repositories only ``flush``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.alert import DEFAULT_COOLDOWN_SECONDS, Alert as AlertORM
from db.repositories.alert_repo import AlertRepository
from db.repositories.base import DEFAULT_LIMIT, MAX_LIMIT
from db.session import get_session
from errors import NotFoundError
from models.schemas_requests import AlertCreate

router = APIRouter(prefix="/alerts", tags=["alerts"])

_SYMBOL_PATTERN = r"^[A-Za-z.\-]+$"
_MIN_COOLDOWN_SECONDS = 0


class AlertOut(BaseModel):
    """An alert configuration returned to the client (mirror of the ORM row)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    symbol: str
    kind: Literal["delta_drift", "pin_risk", "gamma_spike"]
    threshold: float
    tolerance: float | None = None
    dte_window: int | None = None
    portfolio_id: str | None = None
    is_active: bool
    cooldown_seconds: int
    last_evaluated_at: datetime | None = None
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertUpdate(BaseModel):
    """Partial update body for ``PATCH /alerts/{id}``.

    Every field is optional; only provided fields are applied. ``threshold`` and
    ``cooldown_seconds`` keep their validation bounds. ``model_fields_set`` is
    used to distinguish "explicitly set to null" from "omitted".
    """

    model_config = ConfigDict(extra="forbid")

    threshold: float | None = None
    tolerance: float | None = None
    dte_window: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    cooldown_seconds: int | None = Field(default=None, ge=_MIN_COOLDOWN_SECONDS)


def _to_out(row: AlertORM) -> AlertOut:
    return AlertOut(
        id=str(row.id),
        symbol=row.symbol,
        kind=row.kind,  # type: ignore[arg-type]
        threshold=float(row.threshold),
        tolerance=float(row.tolerance) if row.tolerance is not None else None,
        dte_window=row.dte_window,
        portfolio_id=str(row.portfolio_id) if row.portfolio_id is not None else None,
        is_active=row.is_active,
        cooldown_seconds=row.cooldown_seconds,
        last_evaluated_at=row.last_evaluated_at,
        last_triggered_at=row.last_triggered_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _parse_portfolio_id(raw: str | None) -> uuid.UUID | None:
    """Coerce an optional portfolio id string to UUID, or 404 on a bad value."""
    if raw is None:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise NotFoundError(f"portfolio '{raw}' not found") from exc


def _parse_alert_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise NotFoundError(f"alert '{raw}' not found") from exc


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    symbol: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[AlertOut]:
    """List alert configurations, optionally filtered by symbol."""
    repo = AlertRepository(session)
    if symbol:
        rows = await repo.list_by_symbol(symbol)
    else:
        rows = await repo.list(limit=limit, offset=cursor)
    return [_to_out(r) for r in rows]


@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    session: AsyncSession = Depends(get_session),
) -> AlertOut:
    """Create a new alert configuration."""
    repo = AlertRepository(session)
    row = AlertORM(
        symbol=body.symbol.upper().strip(),
        kind=body.kind,
        threshold=Decimal(str(body.threshold)),
        tolerance=Decimal(str(body.tolerance)) if body.tolerance is not None else None,
        dte_window=body.dte_window,
        portfolio_id=_parse_portfolio_id(body.portfolio_id),
        is_active=True,
        cooldown_seconds=DEFAULT_COOLDOWN_SECONDS,
    )
    await repo.add(row)
    return _to_out(row)


@router.patch("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: str,
    body: AlertUpdate,
    session: AsyncSession = Depends(get_session),
) -> AlertOut:
    """Partially update an alert (toggle active, adjust thresholds/cooldown)."""
    repo = AlertRepository(session)
    row = await repo.get(_parse_alert_id(alert_id))
    if row is None:
        raise NotFoundError(f"alert '{alert_id}' not found")

    fields = body.model_fields_set
    if "threshold" in fields and body.threshold is not None:
        row.threshold = Decimal(str(body.threshold))
    if "tolerance" in fields:
        row.tolerance = (
            Decimal(str(body.tolerance)) if body.tolerance is not None else None
        )
    if "dte_window" in fields:
        row.dte_window = body.dte_window
    if "is_active" in fields and body.is_active is not None:
        row.is_active = body.is_active
    if "cooldown_seconds" in fields and body.cooldown_seconds is not None:
        row.cooldown_seconds = body.cooldown_seconds

    await session.flush()
    return _to_out(row)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete an alert configuration (cascades its append-only events)."""
    repo = AlertRepository(session)
    row = await repo.get(_parse_alert_id(alert_id))
    if row is None:
        raise NotFoundError(f"alert '{alert_id}' not found")
    await repo.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
