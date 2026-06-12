"""Common enums shared across the canonical DeltaForge contract.

Every value here is canonical per ARCHITECTURE.md §1 and §4.1 and MUST match
across the API (Pydantic), the SSE stream, the Postgres schema, and the
frontend Zod schemas.
"""

from __future__ import annotations

from enum import Enum


class OptionType(str, Enum):
    """Option right: call or put (wire value, snake_case)."""

    CALL = "call"
    PUT = "put"


class WolframEngine(str, Enum):
    """The ONE canonical engine discriminator (§1 rule 2).

    Values ``wolfram`` and ``numeric_fallback`` are used everywhere:
    DB ``engine_mode``, API ``engine``, frontend ``engine`` and the Python
    ``ComputeSource`` enum. The value ``wolfram`` means a real local Wolfram
    Engine kernel ran it. The aliases ``scipy_fallback``, ``wolfram_kernel``,
    ``fallback`` and ``wolfram_cloud`` are NOT used.
    """

    WOLFRAM = "wolfram"
    NUMERIC_FALLBACK = "numeric_fallback"


class PipelineStage(str, Enum):
    """Canonical pipeline / SSE stage names (§1 rule 5)."""

    MARKET_DATA = "market_data"
    GREEKS = "greeks"
    IV_SURFACE = "iv_surface"
    PORTFOLIO = "portfolio"
    HEDGE = "hedge"
    SCENARIO = "scenario"
    SUMMARY = "summary"


class InstrumentType(str, Enum):
    """Instrument classification for a portfolio position."""

    EQUITY = "equity"
    CALL = "call"
    PUT = "put"
