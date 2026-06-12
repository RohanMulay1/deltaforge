"""``portfolios`` ORM model (ARCHITECTURE.md §9.2).

A portfolio owns many positions (1──* CASCADE). Carries the tenant + timestamp
mixins. Positions live in ``position.py`` to keep files focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, PKMixin, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from db.models.position import Position

# Default settlement currency for a freshly created portfolio.
DEFAULT_BASE_CURRENCY = "USD"


class Portfolio(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "portfolios"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default=DEFAULT_BASE_CURRENCY
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    positions: Mapped[list["Position"]] = relationship(
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
