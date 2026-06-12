"""Watchlist repository (ARCHITECTURE.md §9.3)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.models.watchlist import Watchlist, WatchlistItem
from db.repositories.base import AsyncRepository


class WatchlistRepository(AsyncRepository[Watchlist]):
    """CRUD for watchlists + their items."""

    model = Watchlist

    async def get_with_items(self, entity_id: uuid.UUID) -> Watchlist | None:
        """Return a watchlist with its items eagerly loaded, or ``None``."""
        stmt = (
            select(Watchlist)
            .where(Watchlist.id == entity_id)
            .options(selectinload(Watchlist.items))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_default(self) -> Watchlist | None:
        """Return the most recently created watchlist (single-tenant default)."""
        stmt = (
            select(Watchlist)
            .options(selectinload(Watchlist.items))
            .order_by(Watchlist.created_at.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_item(
        self, watchlist_id: uuid.UUID, symbol: str
    ) -> WatchlistItem | None:
        """Return a specific item by ``(watchlist_id, symbol)``, or ``None``."""
        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.symbol == symbol.upper(),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def add_item(self, item: WatchlistItem) -> WatchlistItem:
        """Add a watchlist item and flush (no commit)."""
        self._session.add(item)
        await self._session.flush()
        return item

    async def delete_item(self, item: WatchlistItem) -> None:
        """Delete a watchlist item and flush (no commit)."""
        await self._session.delete(item)
        await self._session.flush()
