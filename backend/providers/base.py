"""MarketDataProvider protocol + raw DTOs (ARCHITECTURE.md §8.1).

A provider returns **raw** market data only — *never* Greeks. Greeks come from
``WolframService`` for verifiability; provider-supplied Greeks are never
trusted. The frozen dataclass DTOs below are the only shapes a provider may
emit; the pipeline layer maps them onto the wire models (``MarketSnapshot`` /
``OptionQuote``) after Wolfram has priced each contract.

``MarketDataProvider`` is a ``runtime_checkable`` Protocol so a future
Tradier/Polygon implementation (driven by ``httpx.AsyncClient``) slots in
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Quote:
    """A spot quote for an underlying symbol."""

    symbol: str
    price: float
    timestamp: datetime


@dataclass(frozen=True)
class RawContract:
    """A single raw option contract row, as pulled from the provider.

    No Greeks. ``implied_volatility`` is provider-reported decimal IV (0.18 =
    18%); the pipeline re-derives Greeks symbolically rather than trusting any
    provider-side analytics.
    """

    strike: float
    expiry: str  # YYYY-MM-DD
    option_type: str  # "call" | "put"
    bid: float
    ask: float
    last_price: float
    volume: int
    open_interest: int
    implied_volatility: float


@dataclass(frozen=True)
class RawChain:
    """A raw options chain for a single expiry."""

    symbol: str
    expiry: str
    spot_price: float
    timestamp: datetime
    calls: tuple[RawContract, ...] = field(default_factory=tuple)
    puts: tuple[RawContract, ...] = field(default_factory=tuple)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Async provider returning RAW market data only (never Greeks)."""

    name: str

    async def get_spot(self, symbol: str) -> Quote: ...

    async def get_expirations(self, symbol: str) -> tuple[str, ...]: ...

    async def get_chain(self, symbol: str, expiry: str) -> RawChain: ...
