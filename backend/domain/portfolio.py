"""Portfolio domain value objects (ARCHITECTURE.md §8.2).

Internal frozen value objects with a derived ``signed_qty``. At the API
boundary these serialize to the canonical ``PortfolioPosition`` carrying a
single SIGNED ``quantity`` — there is no ``side`` on the wire (§1 rule 6).

This domain ``Position`` is distinct from (and richer than) the minimal
``services.wolfram.dto.Position`` the Wolfram service consumes; ``to_wolfram``
bridges the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from models.schemas_common import InstrumentType
from models.schemas_portfolio import PortfolioPosition

# Contract multipliers (§8.2): one option contract controls 100 shares.
EQUITY_MULTIPLIER = 1
OPTION_MULTIPLIER = 100


class Side(str, Enum):
    """Direction of a position. Maps to the sign of the wire ``quantity``."""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class Position:
    """An immutable portfolio leg.

    ``qty`` is the *unsigned* contract/share count (always > 0); ``side``
    carries direction. ``signed_qty`` derives the canonical signed quantity
    used everywhere downstream (negative = short).
    """

    symbol: str
    instrument: InstrumentType
    qty: int
    side: Side
    cost_basis: float | None = None
    strike: float | None = None
    expiry: str | None = None
    position_id: str | None = None

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError("qty must be a positive count; direction is carried by side")

    @property
    def signed_qty(self) -> int:
        """Signed quantity: negative when short."""
        return self.qty if self.side is Side.LONG else -self.qty

    @property
    def multiplier(self) -> int:
        """Contract multiplier: 100 for options, 1 for equity."""
        return EQUITY_MULTIPLIER if self.instrument is InstrumentType.EQUITY else OPTION_MULTIPLIER

    @property
    def is_equity(self) -> bool:
        return self.instrument is InstrumentType.EQUITY

    # ── Boundary serialization ───────────────────────────────────────────────

    def to_wire(self) -> PortfolioPosition:
        """Serialize to the canonical wire model (signed ``quantity``, no side)."""
        return PortfolioPosition(
            id=self.position_id,
            symbol=self.symbol,
            instrument=self.instrument,
            strike=self.strike,
            expiry=self.expiry,
            quantity=self.signed_qty,
            avg_price=self.cost_basis,
        )

    @classmethod
    def from_wire(cls, wire: PortfolioPosition) -> Position:
        """Reconstruct a domain ``Position`` from a wire ``PortfolioPosition``.

        Splits the signed ``quantity`` back into unsigned ``qty`` + ``side``. A
        zero quantity is rejected (a position must have non-zero exposure).
        """
        if wire.quantity == 0:
            raise ValueError("position quantity must be non-zero")
        side = Side.LONG if wire.quantity > 0 else Side.SHORT
        return cls(
            symbol=wire.symbol,
            instrument=wire.instrument,
            qty=abs(wire.quantity),
            side=side,
            cost_basis=wire.avg_price,
            strike=wire.strike,
            expiry=wire.expiry,
            position_id=wire.id,
        )
