"""CSV header aliases + value coercers (ARCHITECTURE.md §8.3).

Pure, dependency-free helpers shared by the tolerant CSV parser. Keeping the
alias map and coercion rules here (not inline in the parser) keeps the parser
small and makes every rule independently testable.
"""

from __future__ import annotations

from datetime import date, datetime

# ── Header alias map ─────────────────────────────────────────────────────────
# Canonical field name → set of accepted (lower-cased, stripped) header labels.
HEADER_ALIASES: dict[str, frozenset[str]] = {
    "symbol": frozenset({"symbol", "ticker", "underlying", "sym", "root"}),
    "instrument": frozenset(
        {"instrument", "type", "instrument_type", "kind", "asset_type", "right"}
    ),
    "side": frozenset({"side", "direction", "long_short", "buy_sell", "position"}),
    "quantity": frozenset({"quantity", "qty", "contracts", "shares", "size", "amount"}),
    "strike": frozenset({"strike", "strike_price", "k"}),
    "expiry": frozenset({"expiry", "expiration", "exp", "expiration_date", "maturity"}),
    "cost_basis": frozenset(
        {"cost_basis", "avg_price", "price", "cost", "entry_price", "avg_cost"}
    ),
}

# ── Synonym maps ─────────────────────────────────────────────────────────────
INSTRUMENT_SYNONYMS: dict[str, str] = {
    "c": "call",
    "call": "call",
    "calls": "call",
    "p": "put",
    "put": "put",
    "puts": "put",
    "e": "equity",
    "eq": "equity",
    "equity": "equity",
    "stock": "equity",
    "share": "equity",
    "shares": "equity",
}

SIDE_SYNONYMS: dict[str, str] = {
    "long": "long",
    "l": "long",
    "buy": "long",
    "b": "long",
    "bot": "long",
    "+": "long",
    "short": "short",
    "s": "short",
    "sell": "short",
    "sld": "short",
    "-": "short",
}

# Accepted date input formats, tried in order; all normalize to ISO ``YYYY-MM-DD``.
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d %Y",
    "%b %d, %Y",
    "%Y%m%d",
)


def normalize_header(label: str) -> str | None:
    """Map a raw CSV header label onto a canonical field name, or ``None``."""
    cleaned = label.strip().lower().replace(" ", "_").replace("-", "_")
    for canonical, accepted in HEADER_ALIASES.items():
        if cleaned in accepted:
            return canonical
    return None


def coerce_number(raw: str) -> float:
    """Parse a numeric cell, stripping ``$`` and thousands separators.

    Raises:
        ValueError: if the cleaned string is not a valid number.
    """
    cleaned = raw.strip().replace("$", "").replace(",", "").replace(" ", "")
    if not cleaned:
        raise ValueError("empty numeric value")
    return float(cleaned)


def coerce_int(raw: str) -> int:
    """Parse an integer cell (tolerating a trailing ``.0`` and ``$``/``,``)."""
    value = coerce_number(raw)
    if value != int(value):
        raise ValueError(f"expected an integer, got {value}")
    return int(value)


def coerce_instrument(raw: str) -> str:
    """Map an instrument cell to ``call`` | ``put`` | ``equity``.

    Raises:
        ValueError: on an unrecognised instrument token.
    """
    token = raw.strip().lower()
    if token in INSTRUMENT_SYNONYMS:
        return INSTRUMENT_SYNONYMS[token]
    raise ValueError(f"unrecognised instrument: {raw!r}")


def coerce_side(raw: str) -> str:
    """Map a side cell to ``long`` | ``short``.

    Raises:
        ValueError: on an unrecognised side token.
    """
    token = raw.strip().lower()
    if token in SIDE_SYNONYMS:
        return SIDE_SYNONYMS[token]
    raise ValueError(f"unrecognised side: {raw!r}")


def coerce_date_iso(raw: str) -> str:
    """Parse a date cell in any accepted format → ISO ``YYYY-MM-DD``.

    Raises:
        ValueError: if no accepted format matches.
    """
    text = raw.strip()
    if not text:
        raise ValueError("empty date value")
    for fmt in _DATE_FORMATS:
        try:
            parsed: date = datetime.strptime(text, fmt).date()
            return parsed.isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date format: {raw!r}")
