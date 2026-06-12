"""PositionTicket — the single validated entry point for new positions.

(ARCHITECTURE.md §8.3)

Reused by BOTH the add-position UI flow and the tolerant CSV parser (DRY): a
CSV row is coerced into the same field shape and validated by the same model,
so the two paths can never drift.

Rules:
  * ``quantity`` strictly positive (direction carried by ``side``);
  * ``cost_basis`` non-negative when present;
  * ``symbol`` normalised (upper-cased) and whitelisted by pattern;
  * option (``call``/``put``) ⇒ ``strike`` AND ``expiry`` present, expiry not
    in the past;
  * equity ⇒ neither ``strike`` nor ``expiry``.

``.to_position()`` produces the frozen domain ``Position``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.portfolio import Position, Side
from models.schemas_common import InstrumentType

# Symbol whitelist: 1-8 chars, letters plus ``.``/``-`` (matches AnalyzeRequest).
_SYMBOL_PATTERN = re.compile(r"^[A-Za-z.\-]{1,8}$")


def _today_utc() -> date:
    return datetime.now(tz=timezone.utc).date()


class PositionTicket(BaseModel):
    """A fully-validated request to add one position."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, max_length=8)
    instrument: InstrumentType
    side: Side
    quantity: int = Field(gt=0)
    cost_basis: float | None = Field(default=None, ge=0.0)
    strike: float | None = Field(default=None, gt=0.0)
    expiry: str | None = None  # ISO YYYY-MM-DD
    position_id: str | None = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _SYMBOL_PATTERN.match(normalized):
            raise ValueError(f"symbol not whitelisted: {value!r}")
        return normalized

    @field_validator("expiry")
    @classmethod
    def _validate_expiry_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"expiry must be ISO YYYY-MM-DD, got {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _validate_instrument_shape(self) -> PositionTicket:
        is_option = self.instrument in (InstrumentType.CALL, InstrumentType.PUT)
        if is_option:
            if self.strike is None or self.expiry is None:
                raise ValueError("option positions require both strike and expiry")
            expiry_date = datetime.strptime(self.expiry, "%Y-%m-%d").date()
            if expiry_date < _today_utc():
                raise ValueError(f"option expiry is in the past: {self.expiry}")
        else:  # equity
            if self.strike is not None or self.expiry is not None:
                raise ValueError("equity positions must not carry strike or expiry")
        return self

    def to_position(self) -> Position:
        """Build the frozen domain ``Position`` from this validated ticket."""
        return Position(
            symbol=self.symbol,
            instrument=self.instrument,
            qty=self.quantity,
            side=self.side,
            cost_basis=self.cost_basis,
            strike=self.strike,
            expiry=self.expiry,
            position_id=self.position_id,
        )
