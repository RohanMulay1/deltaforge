"""Watchlist router (ARCHITECTURE.md §3, §9).

Endpoints (single-tenant: operate on the default watchlist, created lazily):
    GET    /watchlist           → list[WatchlistItemOut]
    POST   /watchlist           → list[WatchlistItemOut]   (add symbol, idempotent)
    DELETE /watchlist/{symbol}  → list[WatchlistItemOut]   (remove symbol)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.watchlist import (
    DEFAULT_WATCHLIST_NAME,
    Watchlist as WatchlistORM,
    WatchlistItem as WatchlistItemORM,
)
from db.repositories.watchlist_repo import WatchlistRepository
from db.session import get_session
from errors import NotFoundError

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# Symbol normalization bounds (mirror AnalyzeRequest constraints).
_SYMBOL_PATTERN = r"^[A-Za-z.\-]+$"


class WatchlistItemCreate(BaseModel):
    """Add-symbol body (§3 ``WatchlistItem``)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=8, pattern=_SYMBOL_PATTERN)


class WatchlistItemOut(BaseModel):
    """A watchlist row returned to the client."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    symbol: str
    created_at: datetime


def _to_out(item: WatchlistItemORM) -> WatchlistItemOut:
    return WatchlistItemOut(
        id=str(item.id), symbol=item.symbol, created_at=item.created_at
    )


async def _ensure_default(repo: WatchlistRepository) -> WatchlistORM:
    """Return the default watchlist, creating it lazily if none exists."""
    existing = await repo.get_default()
    if existing is not None:
        return existing
    watchlist = WatchlistORM(name=DEFAULT_WATCHLIST_NAME, items=[])
    await repo.add(watchlist)
    return watchlist


@router.get("", response_model=list[WatchlistItemOut])
async def list_watchlist(
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistItemOut]:
    """Return the default watchlist's items."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get_default()
    if watchlist is None:
        return []
    return [_to_out(i) for i in watchlist.items]


@router.post("", response_model=list[WatchlistItemOut])
async def add_watchlist_item(
    body: WatchlistItemCreate,
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistItemOut]:
    """Add a symbol to the default watchlist (idempotent on duplicate symbol)."""
    repo = WatchlistRepository(session)
    watchlist = await _ensure_default(repo)
    symbol = body.symbol.upper().strip()

    existing = await repo.find_item(watchlist.id, symbol)
    if existing is None:
        await repo.add_item(
            WatchlistItemORM(watchlist_id=watchlist.id, symbol=symbol)
        )

    refreshed = await repo.get_with_items(watchlist.id)
    assert refreshed is not None  # just ensured/created in-session
    return [_to_out(i) for i in refreshed.items]


@router.delete("/{symbol}", response_model=list[WatchlistItemOut])
async def remove_watchlist_item(
    symbol: str,
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistItemOut]:
    """Remove a symbol from the default watchlist."""
    repo = WatchlistRepository(session)
    watchlist = await repo.get_default()
    if watchlist is None:
        raise NotFoundError("watchlist not found")

    normalized = symbol.upper().strip()
    item = await repo.find_item(watchlist.id, normalized)
    if item is None:
        raise NotFoundError(f"symbol '{normalized}' not in watchlist")
    await repo.delete_item(item)

    refreshed = await repo.get_with_items(watchlist.id)
    assert refreshed is not None
    return [_to_out(i) for i in refreshed.items]
