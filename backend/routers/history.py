"""Analysis history router (ARCHITECTURE.md §3, §9).

Endpoints:
    GET /history            → Paginated[AnalysisHistoryItem]  (query symbol?,limit,cursor)
    GET /history/{id}       → AnalyzeResponse                 (replayed from JSONB)

History is backed by the append-only ``saved_analyses`` table. ``/history/{id}``
replays the full stored ``AnalyzeResponse`` (the Wolfram-reproducibility payload),
honoring the "stored row is replayable" contract (§9.2).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.saved_analysis import SavedAnalysis
from db.repositories.analysis_repo import SavedAnalysisRepository
from db.repositories.base import DEFAULT_LIMIT, MAX_LIMIT
from db.session import get_session
from errors import NotFoundError, UpstreamDataError
from models.schemas_analyze import AnalyzeResponse

router = APIRouter(prefix="/history", tags=["history"])


class AnalysisHistoryItem(BaseModel):
    """A single history listing row (lightweight projection of an analysis)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    symbol: str
    dte_max: int
    spot_price: float
    expiry_used: str
    engine_mode: str
    order_flow_imbalance: float
    pin_risk_score: float
    risk_summary: str | None = None
    created_at: datetime


class Paginated(BaseModel):
    """Cursor/offset-paginated envelope (§3 ``Paginated[...]``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AnalysisHistoryItem]
    total: int
    limit: int
    next_cursor: str | None = None


def _to_item(row: SavedAnalysis) -> AnalysisHistoryItem:
    return AnalysisHistoryItem(
        id=str(row.id),
        symbol=row.symbol,
        dte_max=row.dte_max,
        spot_price=float(row.spot_price),
        expiry_used=row.expiry_used,
        engine_mode=row.engine_mode,
        order_flow_imbalance=float(row.order_flow_imbalance),
        pin_risk_score=float(row.pin_risk_score),
        risk_summary=row.risk_summary,
        created_at=row.created_at,
    )


def _parse_cursor(cursor: str | None) -> int:
    """Decode the offset cursor (opaque non-negative int); default 0."""
    if not cursor:
        return 0
    try:
        offset = int(cursor)
    except ValueError:
        return 0
    return max(0, offset)


@router.get("", response_model=Paginated)
async def list_history(
    symbol: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Paginated:
    """Return paginated analysis history, optionally filtered by symbol."""
    repo = SavedAnalysisRepository(session)
    offset = _parse_cursor(cursor)
    rows = await repo.list_by_symbol(symbol, limit=limit, offset=offset)
    total = await repo.count_by_symbol(symbol)

    next_offset = offset + len(rows)
    next_cursor = str(next_offset) if next_offset < total else None

    return Paginated(
        items=[_to_item(r) for r in rows],
        total=total,
        limit=limit,
        next_cursor=next_cursor,
    )


@router.get("/{analysis_id}", response_model=AnalyzeResponse)
async def get_history_item(
    analysis_id: str,
    session: AsyncSession = Depends(get_session),
) -> AnalyzeResponse:
    """Replay a stored analysis as a full canonical ``AnalyzeResponse``."""
    try:
        parsed = uuid.UUID(analysis_id)
    except (ValueError, AttributeError) as exc:
        raise NotFoundError(f"analysis '{analysis_id}' not found") from exc

    repo = SavedAnalysisRepository(session)
    row = await repo.get_by_id(parsed)
    if row is None:
        raise NotFoundError(f"analysis '{analysis_id}' not found")
    if not row.full_response:
        # Row exists but predates full-response capture → cannot faithfully replay.
        raise UpstreamDataError(
            f"analysis '{analysis_id}' has no replayable response payload"
        )
    return AnalyzeResponse.model_validate(row.full_response)
