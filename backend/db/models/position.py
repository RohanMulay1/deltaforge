"""``positions`` ORM model (ARCHITECTURE.md §9.2).

Quantity is a SIGNED ``Numeric(18,4)`` (negative = short — §1 rule 6).
``instrument_type`` is constrained to ``{equity, call, put}`` and options must
carry both ``strike`` and ``expiry`` (CHECK). ``source`` ∈ ``{manual, csv}``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, PKMixin, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from db.models.portfolio import Portfolio

# Canonical instrument types (mirror models.InstrumentType wire values).
INSTRUMENT_TYPES: tuple[str, ...] = ("equity", "call", "put")
# Position provenance.
POSITION_SOURCES: tuple[str, ...] = ("manual", "csv")
# Standard contract multipliers.
OPTION_MULTIPLIER = 100
EQUITY_MULTIPLIER = 1


def _in_clause(values: tuple[str, ...]) -> str:
    """Render a SQL ``IN (...)`` value list of single-quoted literals."""
    return ", ".join(f"'{v}'" for v in values)


class Position(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "positions"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    instrument_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    multiplier: Mapped[int] = mapped_column(
        Integer, nullable=False, default=OPTION_MULTIPLIER
    )
    avg_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True, default=None
    )
    strike: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True, default=None
    )
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    implied_vol: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True, default=None
    )
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual")

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")

    __table_args__ = (
        CheckConstraint(
            f"instrument_type IN ({_in_clause(INSTRUMENT_TYPES)})",
            name="instrument_type_valid",
        ),
        CheckConstraint(
            f"source IN ({_in_clause(POSITION_SOURCES)})",
            name="source_valid",
        ),
        # Options must carry both strike and expiry; equities need neither.
        CheckConstraint(
            "(instrument_type = 'equity') "
            "OR (strike IS NOT NULL AND expiry IS NOT NULL)",
            name="option_requires_strike_expiry",
        ),
    )
