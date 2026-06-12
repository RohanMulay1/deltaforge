"""SQLAlchemy 2.0 declarative base + mixins (ARCHITECTURE.md §9.1).

``Base`` carries a stable ``MetaData`` naming convention so Alembic produces
clean, reversible migration names (``ix_/uq_/ck_/fk_/pk_``).

Mixins:
- ``PKMixin``      — UUID primary key (server/Python ``uuid4`` default).
- ``TimestampMixin`` — ``created_at`` / ``updated_at`` (timezone-aware).
- ``TenantMixin``  — nullable, indexed ``user_id`` on EVERY table so a future
  auth layer drops in via a non-destructive ``ALTER`` (no rebuild).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable naming convention → deterministic constraint/index names for Alembic.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with the shared naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp (Python-side default)."""
    return datetime.now(timezone.utc)


class PKMixin:
    """UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Creation + update timestamps (timezone-aware)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )


class TenantMixin:
    """Nullable, indexed ``user_id`` reserved for a future auth layer (§9, §12)."""

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
        default=None,
    )
