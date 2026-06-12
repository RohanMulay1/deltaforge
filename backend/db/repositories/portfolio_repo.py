"""Portfolio repository (ARCHITECTURE.md §9.3)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.models.portfolio import Portfolio
from db.repositories.base import DEFAULT_LIMIT, MAX_LIMIT, AsyncRepository


class PortfolioRepository(AsyncRepository[Portfolio]):
    """CRUD for portfolios. Positions load eagerly via ``selectin``."""

    model = Portfolio

    async def get_with_positions(self, entity_id: uuid.UUID) -> Portfolio | None:
        """Return a portfolio with its positions eagerly loaded, or ``None``."""
        stmt = (
            select(Portfolio)
            .where(Portfolio.id == entity_id)
            .options(selectinload(Portfolio.positions))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list(
        self, *, limit: int = DEFAULT_LIMIT, offset: int = 0
    ) -> list[Portfolio]:
        """Return portfolios newest-first with positions eagerly loaded."""
        bounded = max(1, min(limit, MAX_LIMIT))
        stmt = (
            select(Portfolio)
            .options(selectinload(Portfolio.positions))
            .order_by(Portfolio.created_at.desc())
            .limit(bounded)
            .offset(max(0, offset))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
