"""Position ingestion package: ticket validation + tolerant CSV (ARCHITECTURE.md §8.3)."""

from __future__ import annotations

from domain.ingestion.csv_parser import MAX_ROWS, parse_csv
from domain.ingestion.ticket import PositionTicket

__all__ = [
    "PositionTicket",
    "parse_csv",
    "MAX_ROWS",
]
