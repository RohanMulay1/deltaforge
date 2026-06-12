"""Trade-ticket router (ARCHITECTURE.md §3, §12, WS2).

    POST /trade-ticket -> TradeTicket

EXPORT / PAPER ONLY. This endpoint NEVER routes an order to a broker — it
returns a structured, human-readable ticket blob for the user to export or
paper-trade. The compliance disclaimer is embedded in every ticket (§12).

``TradeTicketRequest`` / ``TradeTicket`` are not part of the WS0 §4 split (no
order-execution models exist in the canonical contract precisely because there
is no execution), so they are defined here as router-local DTOs — mirroring how
``routers/portfolios.py`` declares its own ``PortfolioSummary``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["trade-ticket"])

_DISCLAIMER = "Informational only. Not investment advice. No live execution."
# A ticket is a paper artifact only; this enum makes that explicit on the wire.
_TICKET_KIND = "paper_export"


class TradeTicketLeg(BaseModel):
    """One leg of an export/paper ticket."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=8)
    action: str = Field(pattern=r"^(buy|sell)$")
    quantity: int = Field(gt=0)
    instrument: str = Field(pattern=r"^(equity|call|put)$")
    strike: float | None = None
    expiry: str | None = None
    limit_price: float | None = Field(default=None, ge=0.0)


class TradeTicketRequest(BaseModel):
    """A request to MATERIALIZE (never execute) a trade ticket."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=8)
    legs: list[TradeTicketLeg] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)


class TradeTicket(BaseModel):
    """An export/paper ticket blob. ``executed`` is ALWAYS False (§12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    kind: str  # always "paper_export"
    symbol: str
    legs: list[TradeTicketLeg]
    note: str | None
    blob: str  # human-readable export text
    executed: bool  # invariant: always False — no live execution
    created_at: datetime
    disclaimer: str


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _format_leg(leg: TradeTicketLeg) -> str:
    """Render a single leg as a broker-agnostic export line."""
    parts = [leg.action.upper(), str(leg.quantity), leg.symbol.upper()]
    if leg.instrument in ("call", "put"):
        if leg.strike is not None:
            parts.append(f"{leg.strike:g}{'C' if leg.instrument == 'call' else 'P'}")
        if leg.expiry:
            parts.append(leg.expiry)
    else:
        parts.append("SHARES")
    if leg.limit_price is not None:
        parts.append(f"@ {leg.limit_price:g} LMT")
    else:
        parts.append("@ MKT")
    return " ".join(parts)


def _build_blob(req: TradeTicketRequest, ticket_id: str) -> str:
    """Build the human-readable export blob (paper only)."""
    lines = [
        f"# DeltaForge Paper Ticket {ticket_id}",
        f"# Underlying: {req.symbol.upper()}",
        "# PAPER / EXPORT ONLY — NOT TRANSMITTED TO ANY BROKER",
        "",
    ]
    lines.extend(_format_leg(leg) for leg in req.legs)
    if req.note:
        lines.extend(["", f"# Note: {req.note}"])
    lines.extend(["", f"# {_DISCLAIMER}"])
    return "\n".join(lines)


@router.post("/trade-ticket", response_model=TradeTicket)
async def create_trade_ticket(req: TradeTicketRequest) -> TradeTicket:
    """Materialize an export/paper ticket. NEVER executes an order (§12)."""
    ticket_id = f"DF-{int(_now().timestamp())}-{req.symbol.upper()}"
    logger.info(
        "Trade ticket exported (paper only)",
        extra={"symbol": req.symbol.upper(), "legs": len(req.legs)},
    )
    return TradeTicket(
        ticket_id=ticket_id,
        kind=_TICKET_KIND,
        symbol=req.symbol.upper(),
        legs=req.legs,
        note=req.note,
        blob=_build_blob(req, ticket_id),
        executed=False,  # invariant — no live execution path exists
        created_at=_now(),
        disclaimer=_DISCLAIMER,
    )
