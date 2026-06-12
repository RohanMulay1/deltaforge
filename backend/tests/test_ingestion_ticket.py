"""PositionTicket + alias coercer tests (ARCHITECTURE.md §8.3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.ingestion import aliases
from domain.ingestion.ticket import PositionTicket
from domain.portfolio import Side
from models.schemas_common import InstrumentType

_FUT = "2099-12-18"


# ── PositionTicket ────────────────────────────────────────────────────────────


def test_valid_option_ticket_to_position() -> None:
    ticket = PositionTicket(
        symbol="spy",
        instrument=InstrumentType.CALL,
        side=Side.LONG,
        quantity=5,
        strike=530.0,
        expiry=_FUT,
    )
    assert ticket.symbol == "SPY"  # normalized upper
    pos = ticket.to_position()
    assert pos.signed_qty == 5
    assert pos.strike == 530.0


def test_short_side_signs_quantity() -> None:
    ticket = PositionTicket(
        symbol="SPY",
        instrument=InstrumentType.PUT,
        side=Side.SHORT,
        quantity=3,
        strike=500.0,
        expiry=_FUT,
    )
    assert ticket.to_position().signed_qty == -3


def test_equity_ticket_rejects_strike() -> None:
    with pytest.raises(ValidationError):
        PositionTicket(
            symbol="SPY",
            instrument=InstrumentType.EQUITY,
            side=Side.LONG,
            quantity=100,
            strike=530.0,  # equity must not carry a strike
        )


def test_option_requires_strike_and_expiry() -> None:
    with pytest.raises(ValidationError):
        PositionTicket(
            symbol="SPY",
            instrument=InstrumentType.CALL,
            side=Side.LONG,
            quantity=1,
            strike=530.0,
            # missing expiry
        )


def test_past_expiry_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTicket(
            symbol="SPY",
            instrument=InstrumentType.CALL,
            side=Side.LONG,
            quantity=1,
            strike=530.0,
            expiry="2000-01-01",
        )


def test_non_positive_quantity_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTicket(
            symbol="SPY",
            instrument=InstrumentType.EQUITY,
            side=Side.LONG,
            quantity=0,
        )


def test_negative_cost_basis_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTicket(
            symbol="SPY",
            instrument=InstrumentType.EQUITY,
            side=Side.LONG,
            quantity=1,
            cost_basis=-1.0,
        )


def test_non_whitelisted_symbol_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTicket(
            symbol="SP Y!",
            instrument=InstrumentType.EQUITY,
            side=Side.LONG,
            quantity=1,
        )


def test_malformed_expiry_format_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTicket(
            symbol="SPY",
            instrument=InstrumentType.CALL,
            side=Side.LONG,
            quantity=1,
            strike=530.0,
            expiry="not-a-date",
        )


# ── alias coercers ────────────────────────────────────────────────────────────


def test_normalize_header_aliases() -> None:
    assert aliases.normalize_header("Ticker") == "symbol"
    assert aliases.normalize_header("strike price") == "strike"
    assert aliases.normalize_header("unknown_col") is None


def test_coerce_instrument_synonyms() -> None:
    assert aliases.coerce_instrument("C") == "call"
    assert aliases.coerce_instrument("puts") == "put"
    assert aliases.coerce_instrument("stock") == "equity"


def test_coerce_instrument_unknown_raises() -> None:
    with pytest.raises(ValueError):
        aliases.coerce_instrument("widget")


def test_coerce_side_synonyms() -> None:
    assert aliases.coerce_side("buy") == "long"
    assert aliases.coerce_side("S") == "short"


def test_coerce_side_unknown_raises() -> None:
    with pytest.raises(ValueError):
        aliases.coerce_side("sideways")


def test_coerce_number_strips_symbols() -> None:
    assert aliases.coerce_number("$1,530.50") == 1530.5


def test_coerce_number_empty_raises() -> None:
    with pytest.raises(ValueError):
        aliases.coerce_number("   ")


def test_coerce_int_rejects_fractional() -> None:
    with pytest.raises(ValueError):
        aliases.coerce_int("5.5")


def test_coerce_int_tolerates_trailing_zero() -> None:
    assert aliases.coerce_int("5.0") == 5


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2099-12-18", "2099-12-18"),
        ("12/18/2099", "2099-12-18"),
        ("2099/12/18", "2099-12-18"),
        ("18-Dec-2099", "2099-12-18"),
        ("20991218", "2099-12-18"),
    ],
)
def test_coerce_date_formats(raw: str, expected: str) -> None:
    assert aliases.coerce_date_iso(raw) == expected


def test_coerce_date_unknown_raises() -> None:
    with pytest.raises(ValueError):
        aliases.coerce_date_iso("tomorrow")
