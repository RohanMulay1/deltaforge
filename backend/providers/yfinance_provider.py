"""YFinanceProvider — raw market data via yfinance (ARCHITECTURE.md §8.1).

Split out of the legacy ``market_data_agent.py``: this class *fetches only*. It
returns RAW DTOs (``Quote`` / ``RawChain`` / ``RawContract``) — never Greeks,
never OFI/pin-risk (those move to source-agnostic ``analytics.py``).

Every blocking ``yfinance`` call runs off the event loop through a shared
``ThreadPoolExecutor`` (injected at construction, owned by the app lifespan).
The legacy ``time.sleep`` retry loop is gone — transient retries are handled by
the async ``RetryPolicy``.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yfinance as yf

from providers.base import Quote, RawChain, RawContract
from providers.errors import (
    NoChainDataError,
    ProviderUnavailable,
    SymbolNotFoundError,
    UpstreamDataError,
)
from providers.retry import RetryPolicy

logger = logging.getLogger(__name__)

PROVIDER_NAME = "yfinance"


def _is_transient(exc: Exception) -> bool:
    """Heuristic: network/transport-shaped errors from yfinance are transient.

    yfinance raises plain ``Exception``/``requests`` errors rather than a typed
    hierarchy, so we classify by type. ``ValueError`` (empty history, unknown
    symbol) is deterministic.
    """
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


class YFinanceProvider:
    """Async, off-loop yfinance market-data provider (raw data only)."""

    name: str = PROVIDER_NAME

    def __init__(
        self,
        executor: ThreadPoolExecutor,
        retry: RetryPolicy | None = None,
    ) -> None:
        self._executor = executor
        self._retry = retry or RetryPolicy()

    async def _run(self, fn, *args):  # type: ignore[no-untyped-def]
        """Run a blocking callable on the shared executor, off the loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    # ── Spot ─────────────────────────────────────────────────────────────────

    def _fetch_spot_blocking(self, symbol: str) -> tuple[float, datetime]:
        ticker = yf.Ticker(symbol)
        try:
            hist = ticker.history(period="1d")
        except Exception as exc:  # noqa: BLE001 - classify, then re-raise typed
            if _is_transient(exc):
                raise ProviderUnavailable(f"spot fetch failed for {symbol}") from exc
            raise UpstreamDataError(f"spot fetch failed for {symbol}: {exc}") from exc
        if hist is None or hist.empty:
            raise SymbolNotFoundError(f"no price history for {symbol}")
        price = float(hist["Close"].iloc[-1])
        return price, datetime.now(tz=timezone.utc)

    async def get_spot(self, symbol: str) -> Quote:
        sym = symbol.upper()

        async def _attempt() -> Quote:
            price, ts = await self._run(self._fetch_spot_blocking, sym)
            return Quote(symbol=sym, price=price, timestamp=ts)

        return await self._retry.run(_attempt, op=f"get_spot:{sym}")

    # ── Expirations ──────────────────────────────────────────────────────────

    def _fetch_expirations_blocking(self, symbol: str) -> tuple[str, ...]:
        ticker = yf.Ticker(symbol)
        try:
            expirations = ticker.options
        except Exception as exc:  # noqa: BLE001
            if _is_transient(exc):
                raise ProviderUnavailable(f"expirations fetch failed for {symbol}") from exc
            raise UpstreamDataError(f"expirations fetch failed for {symbol}: {exc}") from exc
        if not expirations:
            raise NoChainDataError(f"no options expirations for {symbol}")
        return tuple(expirations)

    async def get_expirations(self, symbol: str) -> tuple[str, ...]:
        sym = symbol.upper()

        async def _attempt() -> tuple[str, ...]:
            return await self._run(self._fetch_expirations_blocking, sym)

        return await self._retry.run(_attempt, op=f"get_expirations:{sym}")

    # ── Chain ────────────────────────────────────────────────────────────────

    def _fetch_chain_blocking(self, symbol: str, expiry: str) -> RawChain:
        ticker = yf.Ticker(symbol)
        try:
            spot_hist = ticker.history(period="1d")
            chain = ticker.option_chain(expiry)
        except Exception as exc:  # noqa: BLE001
            if _is_transient(exc):
                raise ProviderUnavailable(
                    f"chain fetch failed for {symbol}/{expiry}"
                ) from exc
            raise UpstreamDataError(
                f"chain fetch failed for {symbol}/{expiry}: {exc}"
            ) from exc

        if spot_hist is None or spot_hist.empty:
            raise SymbolNotFoundError(f"no price history for {symbol}")
        spot = float(spot_hist["Close"].iloc[-1])

        calls = self._rows_to_contracts(chain.calls, "call", expiry)
        puts = self._rows_to_contracts(chain.puts, "put", expiry)
        if not calls and not puts:
            raise NoChainDataError(f"empty options chain for {symbol}/{expiry}")

        return RawChain(
            symbol=symbol,
            expiry=expiry,
            spot_price=spot,
            timestamp=datetime.now(tz=timezone.utc),
            calls=calls,
            puts=puts,
        )

    @staticmethod
    def _rows_to_contracts(df, option_type: str, expiry: str) -> tuple[RawContract, ...]:
        """Convert a yfinance options DataFrame into raw contracts.

        No noise filtering here — that is a pipeline/analytics concern. Rows
        with unparseable required fields are skipped, not fatal.
        """
        contracts: list[RawContract] = []
        for _, row in df.iterrows():
            try:
                contracts.append(
                    RawContract(
                        strike=float(row["strike"]),
                        expiry=expiry,
                        option_type=option_type,
                        bid=float(row.get("bid", 0.0) or 0.0),
                        ask=float(row.get("ask", 0.0) or 0.0),
                        last_price=float(row.get("lastPrice", 0.0) or 0.0),
                        volume=int(row.get("volume", 0) or 0),
                        open_interest=int(row.get("openInterest", 0) or 0),
                        implied_volatility=float(row.get("impliedVolatility", 0.0) or 0.0),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping malformed contract row", extra={"error": str(exc)}
                )
                continue
        return tuple(contracts)

    async def get_chain(self, symbol: str, expiry: str) -> RawChain:
        sym = symbol.upper()

        async def _attempt() -> RawChain:
            return await self._run(self._fetch_chain_blocking, sym, expiry)

        return await self._retry.run(_attempt, op=f"get_chain:{sym}/{expiry}")
