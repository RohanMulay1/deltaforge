"""``watchlists`` + ``watchlist_items`` ORM models (ARCHITECTURE.md §9.2).

A watchlist owns many items (1──* CASCADE). ``(watchlist_id, symbol)`` is unique
so a symbol cannot be added twice to the same list.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, PKMixin, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    pass

DEFAULT_WATCHLIST_NAME = "Default"


class Watchlist(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "watchlists"

    name: Mapped[str] = mapped_column(
        String(120), nullable=False, default=DEFAULT_WATCHLIST_NAME
    )

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class WatchlistItem(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "watchlist_items"

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")

    # No explicit name → the MetaData naming convention generates
    # ``uq_watchlist_items_watchlist_id`` (must match migration 0001).
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol"),)
