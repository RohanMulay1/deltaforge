"""Tolerant CSV position importer (ARCHITECTURE.md §8.3).

Parses pasted CSV text into validated positions. Tolerant by design:

  * ``csv.Sniffer`` auto-detects the delimiter (comma / tab / semicolon);
  * headers are matched through the alias map (``aliases.HEADER_ALIASES``);
  * values run through the shared coercers (strip ``$``/``,``, instrument/side
    synonyms, multi-format dates → ISO);
  * EVERY row is validated by the SAME ``PositionTicket`` model the UI uses (DRY);
  * a bad row yields a per-row ``CsvRowError`` and does NOT discard its valid
    siblings;
  * a hard cap of ``MAX_ROWS`` rows guards against pathological input.

Returns a ``CsvImportResult{positions, rejected}``.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Mapping

from pydantic import ValidationError

from domain.ingestion.aliases import (
    coerce_date_iso,
    coerce_instrument,
    coerce_int,
    coerce_number,
    coerce_side,
    normalize_header,
)
from domain.ingestion.ticket import PositionTicket
from models.schemas_requests import CsvImportResult, CsvRowError

logger = logging.getLogger(__name__)

# Hard cap on processed rows (§8.3). Named, not magic.
MAX_ROWS = 1000

_DELIMITERS = ",\t;"
# Equity instrument tokens that mean "no strike/expiry expected".
_EQUITY = "equity"


def _sniff_delimiter(sample: str) -> str:
    """Detect the delimiter; fall back to comma if the Sniffer is unsure."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=_DELIMITERS)
        return dialect.delimiter
    except csv.Error:
        return ","


def _coerce_row(canonical: Mapping[str, str]) -> dict[str, object]:
    """Coerce a single header-normalised row into ``PositionTicket`` kwargs.

    Raises:
        ValueError: on any unrecoverable coercion error (caught per-row).
    """
    raw_symbol = (canonical.get("symbol") or "").strip()
    if not raw_symbol:
        raise ValueError("missing symbol")

    instrument = coerce_instrument(canonical.get("instrument") or "")
    side = coerce_side(canonical.get("side") or "")
    quantity = coerce_int(canonical.get("quantity") or "")

    fields: dict[str, object] = {
        "symbol": raw_symbol,
        "instrument": instrument,
        "side": side,
        "quantity": quantity,
    }

    cost_raw = (canonical.get("cost_basis") or "").strip()
    if cost_raw:
        fields["cost_basis"] = coerce_number(cost_raw)

    if instrument != _EQUITY:
        strike_raw = (canonical.get("strike") or "").strip()
        expiry_raw = (canonical.get("expiry") or "").strip()
        if strike_raw:
            fields["strike"] = coerce_number(strike_raw)
        if expiry_raw:
            fields["expiry"] = coerce_date_iso(expiry_raw)

    return fields


def parse_csv(text: str) -> CsvImportResult:
    """Parse CSV text into validated positions + per-row rejections.

    Args:
        text: raw pasted CSV (with a header row).

    Returns:
        ``CsvImportResult`` — ``positions`` (the survivors, as wire
        ``PortfolioPosition``) and ``rejected`` (per-row ``CsvRowError``).
    """
    stripped = text.strip()
    if not stripped:
        return CsvImportResult(positions=[], rejected=[])

    sample = stripped[:4096]
    delimiter = _sniff_delimiter(sample)
    reader = csv.reader(io.StringIO(stripped), delimiter=delimiter)

    try:
        header_row = next(reader)
    except StopIteration:
        return CsvImportResult(positions=[], rejected=[])

    # Map column index → canonical field name (unknown columns are ignored).
    column_map: dict[int, str] = {}
    for idx, label in enumerate(header_row):
        canonical = normalize_header(label)
        if canonical is not None:
            column_map[idx] = canonical

    positions = []
    rejected: list[CsvRowError] = []

    for offset, row in enumerate(reader):
        row_number = offset + 2  # 1-based, +1 for the header row
        if offset >= MAX_ROWS:
            rejected.append(
                CsvRowError(
                    row_number=row_number,
                    raw={"_": delimiter.join(row)},
                    message=f"row cap of {MAX_ROWS} exceeded; row skipped",
                )
            )
            continue

        canonical_row = {
            column_map[idx]: value
            for idx, value in enumerate(row)
            if idx in column_map
        }
        raw_display = {
            (column_map.get(idx) or f"col_{idx}"): value
            for idx, value in enumerate(row)
        }

        try:
            fields = _coerce_row(canonical_row)
            ticket = PositionTicket(**fields)  # type: ignore[arg-type]
            positions.append(ticket.to_position().to_wire())
        except (ValueError, ValidationError) as exc:
            rejected.append(
                CsvRowError(
                    row_number=row_number,
                    raw=raw_display,
                    message=_format_error(exc),
                )
            )
            continue

    logger.info(
        "CSV import parsed",
        extra={"accepted": len(positions), "rejected": len(rejected)},
    )
    return CsvImportResult(positions=positions, rejected=rejected)


def _format_error(exc: Exception) -> str:
    """Render a concise, user-facing per-row error message."""
    if isinstance(exc, ValidationError):
        parts = [
            f"{'.'.join(str(p) for p in err['loc']) or 'row'}: {err['msg']}"
            for err in exc.errors()
        ]
        return "; ".join(parts)
    return str(exc)
