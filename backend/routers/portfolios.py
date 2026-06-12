"""Portfolio CRUD router (ARCHITECTURE.md §3, §9).

Endpoints (persistence-only; the analyze + csv-import endpoints are owned by
WS2/WS1 respectively and mounted there):
    POST   /portfolios          → Portfolio
    GET    /portfolios          → list[PortfolioSummary]
    GET    /portfolios/{id}     → Portfolio
    PUT    /portfolios/{id}     → Portfolio
    DELETE /portfolios/{id}     → 204

Wire <-> ORM mapping: the canonical wire ``PortfolioPosition`` carries a single
signed ``quantity`` (no ``side`` — §1 rule 6); the ORM ``Position`` stores the
same signed quantity plus ``multiplier``/``source`` provenance.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.portfolio import DEFAULT_BASE_CURRENCY, Portfolio as PortfolioORM
from db.models.position import (
    EQUITY_MULTIPLIER,
    OPTION_MULTIPLIER,
    Position as PositionORM,
)
from db.repositories.portfolio_repo import PortfolioRepository
from db.session import get_session
from errors import NotFoundError
from models.schemas_common import InstrumentType
from models.schemas_portfolio import Portfolio, PortfolioPosition

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


# ── Router-local DTOs (not in WS0 §4) ─────────────────────────────────────────


class PortfolioSummary(BaseModel):
    """Lightweight portfolio listing row (§3 ``list[PortfolioSummary]``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    position_count: int
    base_currency: str
    created_at: datetime
    updated_at: datetime


class PortfolioCreateBody(BaseModel):
    """Create body (mirrors WS0 ``PortfolioCreate`` plus optional currency)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    positions: list[PortfolioPosition] = Field(min_length=1)
    base_currency: str = Field(default=DEFAULT_BASE_CURRENCY, max_length=8)
    notes: str | None = None


class PortfolioUpdate(BaseModel):
    """Update body (§3 ``PUT /portfolios/{id}``). Full-replace semantics."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    positions: list[PortfolioPosition] | None = None
    base_currency: str | None = Field(default=None, max_length=8)
    notes: str | None = None


# ── Mapping helpers ────────────────────────────────────────────────────────────


def _multiplier_for(instrument: InstrumentType) -> int:
    """Return the contract multiplier for the instrument type."""
    return EQUITY_MULTIPLIER if instrument == InstrumentType.EQUITY else OPTION_MULTIPLIER


def _parse_expiry(value: str | None) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` expiry string into a ``date`` (or ``None``)."""
    if not value:
        return None
    return date.fromisoformat(value)


def _to_orm_position(pos: PortfolioPosition) -> PositionORM:
    """Map a wire ``PortfolioPosition`` to a new ORM ``Position`` row."""
    return PositionORM(
        symbol=pos.symbol.upper(),
        instrument_type=pos.instrument.value,
        quantity=Decimal(str(pos.quantity)),
        multiplier=_multiplier_for(pos.instrument),
        avg_price=None if pos.avg_price is None else Decimal(str(pos.avg_price)),
        strike=None if pos.strike is None else Decimal(str(pos.strike)),
        expiry=_parse_expiry(pos.expiry),
        source="manual",
    )


def _to_wire_position(orm: PositionORM) -> PortfolioPosition:
    """Map an ORM ``Position`` back to the canonical wire ``PortfolioPosition``."""
    return PortfolioPosition(
        id=str(orm.id),
        symbol=orm.symbol,
        instrument=InstrumentType(orm.instrument_type),
        strike=None if orm.strike is None else float(orm.strike),
        expiry=orm.expiry.isoformat() if orm.expiry else None,
        quantity=int(orm.quantity),
        avg_price=None if orm.avg_price is None else float(orm.avg_price),
        greeks=None,
        wolfram=None,
    )


def _to_wire_portfolio(orm: PortfolioORM) -> Portfolio:
    """Map a fully-loaded ORM portfolio to the canonical wire ``Portfolio``."""
    return Portfolio(
        id=str(orm.id),
        name=orm.name,
        positions=[_to_wire_position(p) for p in orm.positions],
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def _parse_uuid(raw: str) -> uuid.UUID:
    """Parse a path id to UUID, raising ``NotFoundError`` on a malformed id."""
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise NotFoundError(f"portfolio '{raw}' not found") from exc


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("", response_model=Portfolio, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    body: PortfolioCreateBody,
    session: AsyncSession = Depends(get_session),
) -> Portfolio:
    """Create a portfolio with its initial positions."""
    repo = PortfolioRepository(session)
    portfolio = PortfolioORM(
        name=body.name,
        base_currency=body.base_currency or DEFAULT_BASE_CURRENCY,
        notes=body.notes,
        positions=[_to_orm_position(p) for p in body.positions],
    )
    await repo.add(portfolio)
    return _to_wire_portfolio(portfolio)


@router.get("", response_model=list[PortfolioSummary])
async def list_portfolios(
    session: AsyncSession = Depends(get_session),
) -> list[PortfolioSummary]:
    """Return all portfolios (newest-first) as lightweight summaries."""
    repo = PortfolioRepository(session)
    portfolios = await repo.list()
    return [
        PortfolioSummary(
            id=str(p.id),
            name=p.name,
            position_count=len(p.positions),
            base_currency=p.base_currency,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in portfolios
    ]


@router.get("/{portfolio_id}", response_model=Portfolio)
async def get_portfolio(
    portfolio_id: str,
    session: AsyncSession = Depends(get_session),
) -> Portfolio:
    """Return a single portfolio with its positions."""
    repo = PortfolioRepository(session)
    portfolio = await repo.get_with_positions(_parse_uuid(portfolio_id))
    if portfolio is None:
        raise NotFoundError(f"portfolio '{portfolio_id}' not found")
    return _to_wire_portfolio(portfolio)


@router.put("/{portfolio_id}", response_model=Portfolio)
async def update_portfolio(
    portfolio_id: str,
    body: PortfolioUpdate,
    session: AsyncSession = Depends(get_session),
) -> Portfolio:
    """Update a portfolio's metadata and/or fully replace its positions."""
    repo = PortfolioRepository(session)
    portfolio = await repo.get_with_positions(_parse_uuid(portfolio_id))
    if portfolio is None:
        raise NotFoundError(f"portfolio '{portfolio_id}' not found")

    if body.name is not None:
        portfolio.name = body.name
    if body.base_currency is not None:
        portfolio.base_currency = body.base_currency
    if body.notes is not None:
        portfolio.notes = body.notes
    if body.positions is not None:
        # Full-replace: orphan-cascade removes the old rows on flush.
        portfolio.positions = [_to_orm_position(p) for p in body.positions]

    portfolio.updated_at = datetime.now(timezone.utc)
    await session.flush()
    refreshed = await repo.get_with_positions(portfolio.id)
    assert refreshed is not None  # just updated in-session
    return _to_wire_portfolio(refreshed)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a portfolio (cascades to its positions)."""
    repo = PortfolioRepository(session)
    portfolio = await repo.get(_parse_uuid(portfolio_id))
    if portfolio is None:
        raise NotFoundError(f"portfolio '{portfolio_id}' not found")
    await repo.delete(portfolio)
