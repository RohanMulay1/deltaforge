"""Alert + AlertEvent repositories (ARCHITECTURE.md §9.3).

``AlertRepository`` supports full CRUD (alerts are mutable config: toggle
``is_active``, update thresholds). ``AlertEventRepository`` is APPEND-ONLY — it
omits update/delete, mirroring ``saved_analyses``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from db.models.alert import Alert, AlertEvent
from db.repositories.base import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AsyncRepository,
)


class AlertRepository(AsyncRepository[Alert]):
    """CRUD for alert configurations (mutable)."""

    model = Alert

    async def list_active(self) -> list[Alert]:
        """Return all active alerts (used by the background evaluator)."""
        stmt = (
            select(Alert)
            .where(Alert.is_active.is_(True))
            .order_by(Alert.symbol.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_symbol(self, symbol: str) -> list[Alert]:
        """Return active alerts for a single symbol."""
        stmt = select(Alert).where(
            Alert.symbol == symbol.upper(),
            Alert.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class AlertEventRepository(AsyncRepository[AlertEvent]):
    """Append-only repository for alert firings (omits update/delete)."""

    model = AlertEvent

    async def delete(self, entity: AlertEvent) -> None:  # noqa: D401
        """Disabled: ``alert_events`` is append-only (§9.3)."""
        raise NotImplementedError("alert_events is append-only; delete is forbidden")

    async def list_for_alert(
        self,
        alert_id: uuid.UUID,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> list[AlertEvent]:
        """Return events for one alert, newest-first."""
        bounded = max(1, min(limit, MAX_LIMIT))
        stmt = (
            select(AlertEvent)
            .where(AlertEvent.alert_id == alert_id)
            .order_by(AlertEvent.triggered_at.desc())
            .limit(bounded)
            .offset(max(0, offset))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
