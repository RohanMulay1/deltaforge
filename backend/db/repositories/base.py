"""Generic async repository (ARCHITECTURE.md §9.3).

``AsyncRepository[T]`` provides ``get / list / add / delete`` and ``flush`` —
NEVER ``commit``. Commit/rollback is owned by the request ``get_session``
dependency (unit of work) or the scheduler job. Append-only repositories
subclass and omit ``delete`` (and never expose update).

Business logic depends on the ``Repository`` Protocol, not SQLAlchemy.
"""

from __future__ import annotations

import uuid
from typing import Generic, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import Base

T = TypeVar("T", bound=Base)
T_co = TypeVar("T_co", covariant=True)


class Repository(Protocol[T_co]):
    """Storage-agnostic repository contract (duck-typed for tests/mocks)."""

    async def get(self, entity_id: uuid.UUID) -> T_co | None: ...
    async def list(self, *, limit: int = 100, offset: int = 0) -> list[T_co]: ...
    async def add(self, entity: T_co) -> T_co: ...


# Pagination defaults (named constants — no magic numbers at call sites).
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class AsyncRepository(Generic[T]):
    """Concrete SQLAlchemy implementation of the repository contract.

    Subclasses set ``model``. Methods ``flush`` to assign PKs / surface DB
    errors early, but leave commit to the unit of work.
    """

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get(self, entity_id: uuid.UUID) -> T | None:
        """Return the row by primary key, or ``None``."""
        return await self._session.get(self.model, entity_id)

    async def list(self, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> list[T]:
        """Return rows with bounded pagination (newest-first if timestamped)."""
        bounded = max(1, min(limit, MAX_LIMIT))
        stmt = select(self.model).limit(bounded).offset(max(0, offset))
        if hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())  # type: ignore[attr-defined]
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, entity: T) -> T:
        """Add a new entity and flush (assigns PK; no commit)."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: T) -> None:
        """Delete an entity and flush (no commit)."""
        await self._session.delete(entity)
        await self._session.flush()
