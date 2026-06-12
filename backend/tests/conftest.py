"""Shared pytest fixtures for the DeltaForge backend test suite (WS7).

ALL external systems are mocked — the tests never hit the network, the real
Wolfram kernel, yfinance, Groq, or a live database:

  * ``fake_wolfram`` — a REAL ``WolframService`` whose session pool is stubbed to
    ``live_mode=False``. Every call therefore flows through the LABELED numeric
    fallback (``fallback.py``) and can NEVER emit ``engine="wolfram"`` — exactly
    the honest-fallback guarantee the architecture requires (§5.6).
  * ``fake_market_provider`` — an in-memory provider returning the canned SPY
    chain from ``tests/fixtures/SPY_chain.json`` (no yfinance, no network).
  * ``fake_groq`` — patches the summary node's LLM call so no Groq request is
    made; returns a deterministic narrative.
  * ``test_client`` — a FastAPI ``TestClient`` over a freshly-built app with the
    shared singletons (wolfram / provider / sessionmaker) injected onto
    ``app.state`` and the lifespan bypassed (no kernel boot, no DB engine).

The backend imports are top-level (``from models ...`` etc.), so the backend
directory is placed on ``sys.path`` here and ``asyncio_mode=auto`` (pyproject)
lets ``async def test_*`` run without an explicit marker.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# ── Make the backend package root importable (top-level `from models ...`) ────
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

from core.wolfram_settings import WolframSettings  # noqa: E402
from providers.base import Quote, RawChain, RawContract  # noqa: E402
from providers.errors import SymbolNotFoundError  # noqa: E402
from services.wolfram.service import WolframService  # noqa: E402


# ── Canned SPY chain ──────────────────────────────────────────────────────────


def _load_spy_payload() -> dict[str, Any]:
    return json.loads((_FIXTURES / "SPY_chain.json").read_text(encoding="utf-8"))


def _raw_contracts(rows: Sequence[dict[str, Any]]) -> tuple[RawContract, ...]:
    return tuple(
        RawContract(
            strike=float(r["strike"]),
            expiry=str(r["expiry"]),
            option_type=str(r["option_type"]),
            bid=float(r["bid"]),
            ask=float(r["ask"]),
            last_price=float(r["last_price"]),
            volume=int(r["volume"]),
            open_interest=int(r["open_interest"]),
            implied_volatility=float(r["implied_volatility"]),
        )
        for r in rows
    )


def build_spy_chain() -> RawChain:
    """Construct the canned SPY ``RawChain`` from the fixture JSON."""
    payload = _load_spy_payload()
    return RawChain(
        symbol=str(payload["symbol"]),
        expiry=str(payload["expiry"]),
        spot_price=float(payload["spot_price"]),
        timestamp=datetime(2026, 6, 12, tzinfo=timezone.utc),
        calls=_raw_contracts(payload["calls"]),
        puts=_raw_contracts(payload["puts"]),
    )


@pytest.fixture
def spy_chain() -> RawChain:
    return build_spy_chain()


@pytest.fixture
def spy_payload() -> dict[str, Any]:
    return _load_spy_payload()


# ── Fake market-data provider (no yfinance, no network) ───────────────────────


class FakeMarketProvider:
    """In-memory ``MarketDataProvider`` returning the canned SPY chain.

    Implements the §8.1 protocol surface (``get_spot`` / ``get_expirations`` /
    ``get_chain``). Unknown symbols raise ``SymbolNotFoundError`` so the router
    404 path is exercised.
    """

    name = "fake"

    def __init__(self, chain: RawChain) -> None:
        self._chain = chain

    async def get_spot(self, symbol: str) -> Quote:
        if symbol.upper() != self._chain.symbol.upper():
            raise SymbolNotFoundError(f"unknown symbol: {symbol}")
        return Quote(
            symbol=self._chain.symbol,
            price=self._chain.spot_price,
            timestamp=self._chain.timestamp,
        )

    async def get_expirations(self, symbol: str) -> tuple[str, ...]:
        if symbol.upper() != self._chain.symbol.upper():
            raise SymbolNotFoundError(f"unknown symbol: {symbol}")
        return (self._chain.expiry,)

    async def get_chain(self, symbol: str, expiry: str) -> RawChain:
        if symbol.upper() != self._chain.symbol.upper():
            raise SymbolNotFoundError(f"unknown symbol: {symbol}")
        return self._chain


@pytest.fixture
def fake_market_provider(spy_chain: RawChain) -> FakeMarketProvider:
    return FakeMarketProvider(spy_chain)


# ── Fake Wolfram session pool → forces numeric_fallback ───────────────────────


class _DeadPool:
    """A session pool that is never live, so every eval degrades to fallback.

    Mirrors the public surface ``WolframService`` touches: ``live_mode`` is
    ``False`` and ``reason`` is set, so ``_try_kernel`` short-circuits to the
    labeled numeric fallback WITHOUT ever attempting a kernel call.
    """

    def __init__(self, reason: str = "kill_switch") -> None:
        self.live_mode = False
        self.reason = reason
        self.pool_size = 0
        self.healthy_sessions = 0

    async def start(self) -> None:  # pragma: no cover - trivial
        return None

    async def stop(self) -> None:  # pragma: no cover - trivial
        return None

    async def evaluate(self, operation: str, payload_expr: str) -> Any:  # noqa: ARG002
        raise AssertionError("evaluate must not be called when live_mode is False")


def build_fake_wolfram(reason: str = "kill_switch") -> WolframService:
    """A real ``WolframService`` wired to a dead pool (always numeric_fallback)."""
    settings = WolframSettings(wolfram_enabled=False)
    service = WolframService(settings=settings, pool=_DeadPool(reason=reason))  # type: ignore[arg-type]
    return service


@pytest.fixture
def fake_wolfram() -> WolframService:
    """A WolframService that ALWAYS uses the labeled numeric fallback."""
    return build_fake_wolfram()


# ── Fake Groq (no network LLM call) ───────────────────────────────────────────


@pytest.fixture
def fake_groq(monkeypatch: pytest.MonkeyPatch) -> str:
    """Patch the summary node's Groq call to a deterministic narrative."""
    summary = "Deterministic test summary: delta exposure is modest; hold the hedge."

    async def _fake_generate_summary(prompt: str) -> str:  # noqa: ARG001
        return summary

    import graph.nodes.stages as stages

    monkeypatch.setattr(stages, "_generate_summary", _fake_generate_summary)
    return summary


# ── FastAPI TestClient with deps injected (lifespan bypassed) ─────────────────


@pytest.fixture
def test_client(
    fake_wolfram: WolframService,
    fake_market_provider: FakeMarketProvider,
) -> Iterator[Any]:
    """A ``TestClient`` over the real app with shared singletons injected.

    The lifespan (kernel boot, DB engine, scheduler) is bypassed by overriding
    ``app.router.lifespan_context`` with a no-op; the singletons normally created
    there are placed directly on ``app.state``. ``sessionmaker`` is ``None`` so
    persistence is a no-op (the analyze path tolerates a missing DB, §9.3).
    """
    from contextlib import asynccontextmanager

    from fastapi.testclient import TestClient

    import main as main_module

    app = main_module.create_app()

    @asynccontextmanager
    async def _noop_lifespan(_app: Any):  # type: ignore[no-untyped-def]
        yield

    app.router.lifespan_context = _noop_lifespan  # type: ignore[assignment]
    app.state.wolfram = fake_wolfram
    app.state.market_provider = fake_market_provider
    app.state.sessionmaker = None
    app.state.scheduler = None

    with TestClient(app) as client:
        yield client
