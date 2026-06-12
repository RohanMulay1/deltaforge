"""``alerts`` + ``alert_events`` ORM models (ARCHITECTURE.md §9.2).

An alert owns many events (1──* CASCADE). ``alert_events`` is APPEND-ONLY: its
repository omits update/delete (§9.3). ``kind`` is a Postgres ENUM
(``alert_kind``) ∈ ``{delta_drift, pin_risk, gamma_spike}``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, PKMixin, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    pass

# Canonical alert kinds (mirror AlertCreate.kind literal).
ALERT_KINDS: tuple[str, ...] = ("delta_drift", "pin_risk", "gamma_spike")
ALERT_KIND_ENUM_NAME = "alert_kind"
DEFAULT_COOLDOWN_SECONDS = 3600

# Shared ENUM type. ``create_type=False`` — the enum is created explicitly in
# migration 0001 so Alembic owns its lifecycle (no implicit emit on table DDL).
alert_kind_enum = PGEnum(
    *ALERT_KINDS,
    name=ALERT_KIND_ENUM_NAME,
    create_type=False,
)


class Alert(PKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "alerts"

    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        default=None,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(alert_kind_enum, nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    tolerance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True, default=None
    )
    dte_window: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cooldown_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_COOLDOWN_SECONDS
    )
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AlertEvent(PKMixin, TenantMixin, TimestampMixin, Base):
    """APPEND-ONLY audit row for a single alert firing."""

    __tablename__ = "alert_events"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    observed_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    threshold_at_trigger: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    saved_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("saved_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        default=None,
    )

    alert: Mapped["Alert"] = relationship(back_populates="events")
