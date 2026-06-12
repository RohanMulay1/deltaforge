"""Agent 1 — Market Data Agent.

Pulls the nearest weekly options chain for a given symbol via yfinance,
applies noise filters, computes order-flow imbalance and pin-risk score,
and returns a validated OptionsChainPayload.

No math emulation. All calculations here are pure data aggregation.
Wolfram handles pricing/Greeks in Agent 2.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf
from pydantic import ValidationError

from models.schemas import OptionContract, OptionsChainPayload

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MIN_VOLUME = 100
MIN_BID = 0.01
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


def _nearest_expiry_within_dte(ticker: yf.Ticker, dte_max: int) -> str:
    """Return the nearest expiry string (YYYY-MM-DD) within dte_max days."""
    expirations = ticker.options  # tuple of date strings
    if not expirations:
        raise ValueError(f"No options expirations available for {ticker.ticker}")

    today = datetime.now(tz=timezone.utc).date()
    for exp_str in expirations:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        dte = (exp_date - today).days
        if 0 < dte <= dte_max:
            logger.info(
                "Selected expiry",
                extra={"expiry": exp_str, "dte": dte, "dte_max": dte_max},
            )
            return exp_str

    # Fallback: return the nearest expiry regardless of DTE
    fallback = expirations[0]
    logger.warning(
        "No expiry within DTE window; using nearest available",
        extra={"fallback_expiry": fallback, "dte_max": dte_max},
    )
    return fallback


def _filter_contracts(df, option_type: str, expiry: str) -> list[OptionContract]:
    """Convert a yfinance options DataFrame to a list of OptionContract, applying noise filters."""
    filtered = df[(df["volume"] >= MIN_VOLUME) & (df["bid"] >= MIN_BID)].copy()

    contracts: list[OptionContract] = []
    for _, row in filtered.iterrows():
        try:
            contracts.append(
                OptionContract(
                    strike=float(row["strike"]),
                    expiry=expiry,
                    option_type=option_type,
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    last_price=float(row.get("lastPrice", 0.0)),
                    volume=int(row["volume"]),
                    open_interest=int(row.get("openInterest", 0)),
                    implied_volatility=float(row.get("impliedVolatility", 0.0)),
                )
            )
        except (ValidationError, KeyError, ValueError) as exc:
            logger.warning("Skipping malformed contract row", extra={"error": str(exc)})
            continue

    return contracts


def _compute_order_flow_imbalance(calls: list[OptionContract], puts: list[OptionContract]) -> float:
    call_volume = sum(c.volume for c in calls)
    put_volume = sum(p.volume for p in puts)
    total = call_volume + put_volume
    if total == 0:
        return 0.0
    return (call_volume - put_volume) / total


def _compute_pin_risk_score(
    calls: list[OptionContract],
    puts: list[OptionContract],
    spot_price: float,
) -> float:
    """Score [0,1] — how close the max-OI strike is to spot.

    1.0 = max-OI strike exactly equals spot (maximum pin risk).
    0.0 = max-OI strike is far from spot.
    Proximity window is ±10% of spot.
    """
    all_contracts = calls + puts
    if not all_contracts:
        return 0.0

    max_oi_contract = max(all_contracts, key=lambda c: c.open_interest)
    distance = abs(max_oi_contract.strike - spot_price)
    window = spot_price * 0.10  # 10% of spot as normalizing window
    score = max(0.0, 1.0 - (distance / window))
    return round(min(score, 1.0), 4)


def fetch_options_chain(symbol: str, dte_max: int = 7) -> OptionsChainPayload:
    """Fetch and return a validated OptionsChainPayload for `symbol`.

    Args:
        symbol: Ticker symbol (e.g. "SPY", "QQQ").
        dte_max: Maximum days-to-expiry for the near-term filter.

    Returns:
        OptionsChainPayload — fully validated Pydantic model.

    Raises:
        ValueError: If no viable options data is found after filtering.
        RuntimeError: If yfinance fails after all retries.
    """
    logger.info("Starting options chain fetch", extra={"symbol": symbol, "dte_max": dte_max})

    ticker = yf.Ticker(symbol)

    # Retry loop for transient yfinance failures
    spot_price: Optional[float] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            hist = ticker.history(period="1d")
            if hist.empty:
                raise ValueError(f"Empty price history for {symbol}")
            spot_price = float(hist["Close"].iloc[-1])
            break
        except Exception as exc:
            logger.warning(
                "Failed to fetch spot price",
                extra={"symbol": symbol, "attempt": attempt, "error": str(exc)},
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Could not fetch spot price for {symbol} after {MAX_RETRIES} attempts"
                ) from exc
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    assert spot_price is not None

    expiry = _nearest_expiry_within_dte(ticker, dte_max)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            chain = ticker.option_chain(expiry)
            break
        except Exception as exc:
            logger.warning(
                "Failed to fetch option chain",
                extra={"symbol": symbol, "expiry": expiry, "attempt": attempt, "error": str(exc)},
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Could not fetch option chain for {symbol}/{expiry} after {MAX_RETRIES} attempts"
                ) from exc
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    calls = _filter_contracts(chain.calls, "call", expiry)
    puts = _filter_contracts(chain.puts, "put", expiry)

    if not calls and not puts:
        raise ValueError(
            f"No contracts passed noise filters for {symbol}/{expiry}. "
            f"Filters: volume>={MIN_VOLUME}, bid>={MIN_BID}"
        )

    ofi = _compute_order_flow_imbalance(calls, puts)
    pin_risk = _compute_pin_risk_score(calls, puts, spot_price)

    payload = OptionsChainPayload(
        symbol=symbol.upper(),
        spot_price=spot_price,
        timestamp=datetime.now(tz=timezone.utc),
        expiry_used=expiry,
        near_expiry_filter_used=f"DTE <= {dte_max} days (nearest available: {expiry})",
        calls=calls,
        puts=puts,
        order_flow_imbalance=round(ofi, 4),
        pin_risk_score=pin_risk,
    )

    logger.info(
        "Options chain fetch complete",
        extra={
            "symbol": symbol,
            "expiry": expiry,
            "calls_filtered": len(calls),
            "puts_filtered": len(puts),
            "ofi": ofi,
            "pin_risk": pin_risk,
        },
    )

    return payload
