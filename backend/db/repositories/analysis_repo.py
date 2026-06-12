"""SavedAnalysis repository — APPEND-ONLY (ARCHITECTURE.md §9.3).

This repository intentionally OMITS update and delete: ``saved_analyses`` is an
audit + Wolfram-reproducibility table. Only ``add`` / read paths are exposed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from db.models.saved_analysis import SavedAnalysis
from db.repositories.base import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AsyncRepository,
)


class SavedAnalysisRepository(AsyncRepository[SavedAnalysis]):
    """Append-only repository for persisted analyses.

    ``delete`` is overridden to raise so callers can never violate the
    append-only invariant. There is no update method.
    """

    model = SavedAnalysis

    async def delete(self, entity: SavedAnalysis) -> None:  # noqa: D401
        """Disabled: ``saved_analyses`` is append-only (§9.3)."""
        raise NotImplementedError("saved_analyses is append-only; delete is forbidden")

    async def list_by_symbol(
        self,
        symbol: str | None,
        *,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> list[SavedAnalysis]:
        """Return analyses newest-first, optionally filtered by symbol."""
        bounded = max(1, min(limit, MAX_LIMIT))
        stmt = select(SavedAnalysis).order_by(SavedAnalysis.created_at.desc())
        if symbol:
            stmt = stmt.where(SavedAnalysis.symbol == symbol.upper())
        stmt = stmt.limit(bounded).offset(max(0, offset))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_symbol(self, symbol: str | None) -> int:
        """Return the total count of analyses (optionally symbol-filtered)."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(SavedAnalysis)
        if symbol:
            stmt = stmt.where(SavedAnalysis.symbol == symbol.upper())
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_by_id(self, entity_id: uuid.UUID) -> SavedAnalysis | None:
        """Alias for ``get`` with a domain-meaningful name."""
        return await self.get(entity_id)
