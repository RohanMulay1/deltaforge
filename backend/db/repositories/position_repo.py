"""Position repository (ARCHITECTURE.md §9.3)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from db.models.position import Position
from db.repositories.base import AsyncRepository


class PositionRepository(AsyncRepository[Position]):
    """CRUD for positions, scoped by portfolio."""

    model = Position

    async def list_for_portfolio(self, portfolio_id: uuid.UUID) -> list[Position]:
        """Return all positions belonging to a portfolio."""
        stmt = (
            select(Position)
            .where(Position.portfolio_id == portfolio_id)
            .order_by(Position.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_portfolio(self, portfolio_id: uuid.UUID) -> None:
        """Bulk-delete all positions for a portfolio (used on full replace)."""
        await self._session.execute(
            sa_delete(Position).where(Position.portfolio_id == portfolio_id)
        )
        await self._session.flush()
