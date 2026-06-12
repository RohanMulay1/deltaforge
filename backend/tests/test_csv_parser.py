"""Tolerant CSV importer tests (ARCHITECTURE.md §8.3).

Acceptance (WS1): per-row errors, valid rows survive sibling failures,
tab/comma/semicolon sniffing, alias + date coercion, 1000-row cap.
"""

from __future__ import annotations

from domain.ingestion import aliases
from domain.ingestion.csv_parser import MAX_ROWS, parse_csv
from models.schemas_common import InstrumentType

# A far-future expiry so the "not in the past" rule always passes.
_FUT = "2099-12-18"


def test_parses_basic_comma_csv() -> None:
    csv = (
        "symbol,instrument,side,quantity,strike,expiry\n"
        f"SPY,call,long,5,530,{_FUT}\n"
    )
    result = parse_csv(csv)
    assert len(result.positions) == 1
    assert result.rejected == []
    pos = result.positions[0]
    assert pos.symbol == "SPY"
    assert pos.quantity == 5
    assert pos.instrument is InstrumentType.CALL


def test_short_position_becomes_negative_quantity() -> None:
    csv = (
        "symbol,instrument,side,quantity,strike,expiry\n"
        f"SPY,put,short,3,520,{_FUT}\n"
    )
    result = parse_csv(csv)
    assert result.positions[0].quantity == -3


def test_tab_delimiter_sniffed() -> None:
    csv = (
        "symbol\tinstrument\tside\tquantity\tstrike\texpiry\n"
        f"SPY\tcall\tlong\t2\t530\t{_FUT}\n"
    )
    result = parse_csv(csv)
    assert len(result.positions) == 1
    assert result.positions[0].quantity == 2


def test_semicolon_delimiter_sniffed() -> None:
    csv = (
        "symbol;instrument;side;quantity;strike;expiry\n"
        f"SPY;call;long;1;530;{_FUT}\n"
    )
    result = parse_csv(csv)
    assert len(result.positions) == 1


def test_header_aliases_resolved() -> None:
    # ticker/right/qty/strike_price/expiration/direction synonyms.
    csv = (
        "ticker,right,direction,qty,strike_price,expiration\n"
        f"AAPL,C,B,4,180,{_FUT}\n"
    )
    result = parse_csv(csv)
    assert len(result.positions) == 1
    pos = result.positions[0]
    assert pos.symbol == "AAPL"
    assert pos.instrument is InstrumentType.CALL
    assert pos.quantity == 4


def test_dollar_and_comma_stripped_from_numbers() -> None:
    csv = (
        "symbol,instrument,side,quantity,strike,expiry,cost_basis\n"
        f'SPY,call,long,1,"1,530",{_FUT},$12.50\n'
    )
    result = parse_csv(csv)
    assert len(result.positions) == 1
    assert result.positions[0].strike == 1530.0
    assert result.positions[0].avg_price == 12.5


def test_us_date_format_coerced_to_iso() -> None:
    csv = (
        "symbol,instrument,side,quantity,strike,expiry\n"
        "SPY,call,long,1,530,12/18/2099\n"
    )
    result = parse_csv(csv)
    assert result.positions[0].expiry == "2099-12-18"


def test_per_row_error_does_not_discard_valid_siblings() -> None:
    csv = (
        "symbol,instrument,side,quantity,strike,expiry\n"
        f"SPY,call,long,5,530,{_FUT}\n"  # valid
        "BADROW,call,long,notanumber,530,2099-12-18\n"  # bad quantity
        f"QQQ,put,short,2,400,{_FUT}\n"  # valid
    )
    result = parse_csv(csv)
    assert len(result.positions) == 2
    assert len(result.rejected) == 1
    assert result.rejected[0].row_number == 3


def test_missing_symbol_rejected() -> None:
    csv = (
        "symbol,instrument,side,quantity,strike,expiry\n"
        f",call,long,1,530,{_FUT}\n"
    )
    result = parse_csv(csv)
    assert result.positions == []
    assert len(result.rejected) == 1
    assert "symbol" in result.rejected[0].message.lower()


def test_option_without_strike_rejected() -> None:
    csv = (
        "symbol,instrument,side,quantity,expiry\n"
        f"SPY,call,long,1,{_FUT}\n"  # no strike column at all
    )
    result = parse_csv(csv)
    assert result.positions == []
    assert len(result.rejected) == 1


def test_equity_row_has_no_strike_or_expiry() -> None:
    csv = "symbol,instrument,side,quantity\nSPY,equity,long,100\n"
    result = parse_csv(csv)
    assert len(result.positions) == 1
    pos = result.positions[0]
    assert pos.instrument is InstrumentType.EQUITY
    assert pos.strike is None
    assert pos.expiry is None


def test_empty_input_returns_empty_result() -> None:
    result = parse_csv("   \n  ")
    assert result.positions == []
    assert result.rejected == []


def test_header_only_returns_empty() -> None:
    result = parse_csv("symbol,instrument,side,quantity\n")
    assert result.positions == []
    assert result.rejected == []


def test_row_cap_enforced() -> None:
    header = "symbol,instrument,side,quantity\n"
    body = "".join(f"SPY,equity,long,{i + 1}\n" for i in range(MAX_ROWS + 5))
    result = parse_csv(header + body)
    # Exactly MAX_ROWS processed; the extra rows are rejected with a cap message.
    assert len(result.positions) == MAX_ROWS
    assert len(result.rejected) == 5
    assert "cap" in result.rejected[0].message.lower()


def test_unknown_columns_ignored() -> None:
    csv = (
        "symbol,instrument,side,quantity,note,random\n"
        "SPY,equity,long,10,hello,xyz\n"
    )
    result = parse_csv(csv)
    assert len(result.positions) == 1
