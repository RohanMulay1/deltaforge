"""Pure mappers: internal DTOs -> canonical wire models (ARCHITECTURE.md §4).

Every function here is PURE (no I/O, no kernel, no provider). They translate:

  * ``WolframEvaluation`` (internal) -> ``WolframComputation`` (wire, §4.4),
  * the WS1 provider ``RawChain`` -> per-contract ``OptionQuote`` + ``IVStats``,
  * the WS0 wire ``PortfolioPosition`` -> the Wolfram ``Position`` DTO,
  * the Wolfram ``EngineStatusDTO`` -> the wire ``EngineStatus``.

Keeping these pure means the staged pipeline (``stages.py``) and the routers can
both reuse them, and they are trivially unit-testable.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone

from analytics import (
    compute_max_pain_strike,
    compute_order_flow_imbalance,
    compute_pin_risk_score,
)
from domain.portfolio import OPTION_MULTIPLIER, Position as DomainPosition
from models.schemas_common import InstrumentType, OptionType, WolframEngine
from models.schemas_greeks import Greeks
from models.schemas_market import IVStats, MarketSnapshot, OptionQuote
from models.schemas_portfolio import PortfolioPosition
from models.schemas_wolfram import EngineStatus, WolframComputation
from providers.base import RawChain, RawContract
from services.wolfram.dto import (
    ComputeSource,
    GreeksValues,
    Position as WolframPosition,
    WolframEvaluation,
)

# Default annualized risk-free rate when none supplied (display/pricing input).
DEFAULT_RISK_FREE_RATE = 0.043
# Calendar days per year for the year-fraction conversion (matches BS theta /365).
_DAYS_PER_YEAR = 365.0
# Minimum time-to-expiry (in days) used for pricing — floors 0-DTE/same-day
# expiries away from the Black-Scholes T->0 singularity (avoids div-by-zero
# Power::infy / Indeterminate kernel messages on every contract).
_MIN_TTE_DAYS = 1.0
# Per-contract theta is reported per-YEAR by the kernel; UI shows per-day.
_THETA_PER_DAY_DIVISOR = _DAYS_PER_YEAR
# Vega from the builder is per 1.0 vol; the contract reports per 0.01 IV (§4.2).
_VEGA_PER_VOL_POINT = 0.01


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── Humanized labels for each operation (the explain-drawer title) ────────────

_OPERATION_LABELS: dict[str, str] = {
    "contract_greeks": "Contract Greeks (symbolic D[BS, ·])",
    "portfolio_greeks": "Portfolio Greeks (Total[bsGreeks @@@ book])",
    "delta_neutral_hedge": "Delta-Neutral Hedge (NMinimize)",
    "pnl_surface": "Scenario P&L Surface (symbolic pnl[S, σ, T])",
    "health_canary": "Engine Canary (1 + 1)",
}


def humanize_operation(operation: str) -> str:
    """Return a human-readable label for a WolframService operation."""
    return _OPERATION_LABELS.get(operation, operation.replace("_", " ").title())


# ── WolframEvaluation (internal) -> WolframComputation (wire) — §4.4 ───────────


def _scalar_result(result: object) -> float | None:
    """Extract a single numeric result if the evaluation produced a scalar."""
    if isinstance(result, bool):
        return None
    if isinstance(result, (int, float)):
        value = float(result)
        return value if math.isfinite(value) else None
    return None


def evaluation_to_computation(
    evaluation: WolframEvaluation,
    *,
    inputs: dict[str, float | str] | None = None,
    label: str | None = None,
    result_numeric: float | None = None,
) -> WolframComputation:
    """Map an internal ``WolframEvaluation`` to the wire ``WolframComputation``.

    ``inputs``/``result_numeric``/``label`` override the derived defaults when a
    caller has richer context (e.g. the exact S,K,r,σ,T fed to a contract).
    """
    error: str | None = None
    if evaluation.messages:
        error = "; ".join(f"{tag}: {msg}" for tag, msg in evaluation.messages)
    elif not evaluation.succeeded:
        error = "evaluation did not succeed"

    numeric = result_numeric
    if numeric is None:
        numeric = _scalar_result(evaluation.result)

    engine = (
        WolframEngine.WOLFRAM
        if evaluation.source is ComputeSource.WOLFRAM
        else WolframEngine.NUMERIC_FALLBACK
    )

    return WolframComputation(
        label=label or humanize_operation(evaluation.operation),
        expression=evaluation.wl_input,
        engine=engine,
        inputs=inputs or {},
        result_raw=evaluation.wl_output,
        result_numeric=numeric,
        evaluated=evaluation.source is ComputeSource.WOLFRAM and evaluation.succeeded,
        duration_ms=evaluation.kernel_ms,
        fallback_reason=evaluation.fallback_reason,
        error=error,
        evaluated_at=evaluation.evaluated_at,
    )


# ── EngineStatusDTO -> wire EngineStatus (§4.9) ───────────────────────────────


def engine_status_to_wire(dto: object) -> EngineStatus:
    """Map the internal ``EngineStatusDTO`` to the wire ``EngineStatus``.

    Typed as ``object`` to avoid importing the service module here (keeps this a
    pure, dependency-light mapper). The DTO duck-types the required attributes.
    """
    engine = getattr(dto, "engine_in_use")
    engine_value = engine.value if hasattr(engine, "value") else str(engine)
    return EngineStatus(
        wolfram_available=bool(getattr(dto, "wolfram_available")),
        engine_in_use=WolframEngine(engine_value),
        kernel_version=getattr(dto, "kernel_version", None),
        pool_size=int(getattr(dto, "pool_size", 0)),
        healthy_sessions=int(getattr(dto, "healthy_sessions", 0)),
        last_probe_ms=getattr(dto, "last_probe_ms", None),
        reason=getattr(dto, "reason", None),
        note=getattr(dto, "note", ""),
        last_checked=getattr(dto, "last_checked", _now()),
    )


# ── Greeks DTO -> wire Greeks (with per-contract unit scaling) ────────────────


def greeks_values_to_wire(values: GreeksValues) -> Greeks:
    """Map a per-unit ``GreeksValues`` (theta/year, vega/vol) to wire ``Greeks``.

    The wire contract reports theta per-day and vega per 0.01 IV (§4.2).
    """
    return Greeks(
        delta=values.delta,
        gamma=values.gamma,
        theta=values.theta / _THETA_PER_DAY_DIVISOR,
        vega=values.vega * _VEGA_PER_VOL_POINT,
        rho=values.rho,
    )


# ── Date / DTE helpers ────────────────────────────────────────────────────────


def years_to_expiry(expiry: str, *, now: datetime | None = None) -> float:
    """Year-fraction from now to an ISO ``YYYY-MM-DD`` expiry (>= 0)."""
    ref = now or _now()
    try:
        exp = datetime.strptime(expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    delta_days = (exp - ref).total_seconds() / 86400.0
    # Floor at 1 day: a 0-DTE (same-day) expiry gives T->0, and the Black-Scholes
    # d1 = (...)/(sig*Sqrt[T]) then divides by zero -> Power::infy / Indeterminate
    # kernel messages on every contract. Flooring keeps the symbolic eval clean
    # (matches the legacy agent's max(dte, 1) convention).
    return max(delta_days, _MIN_TTE_DAYS) / _DAYS_PER_YEAR


def dte_for_expiry(expiry: str, *, now: datetime | None = None) -> int:
    """Integer days-to-expiry for an ISO expiry (>= 0)."""
    return int(round(years_to_expiry(expiry, now=now) * _DAYS_PER_YEAR))


# ── Wire PortfolioPosition -> Wolfram Position DTO ────────────────────────────


def wire_position_to_wolfram(
    pos: PortfolioPosition,
    *,
    spot: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
    sigma: float | None = None,
    now: datetime | None = None,
) -> WolframPosition:
    """Bridge a wire ``PortfolioPosition`` to the minimal Wolfram ``Position``.

    ``quantity`` is signed on the wire; the Wolfram DTO consumes ``signed_qty``
    directly. Options carry strike/σ/T; equity is the degenerate case.
    """
    instrument = pos.instrument.value
    is_equity = pos.instrument is InstrumentType.EQUITY
    multiplier = 1.0 if is_equity else float(OPTION_MULTIPLIER)
    t = years_to_expiry(pos.expiry, now=now) if (pos.expiry and not is_equity) else None
    return WolframPosition(
        symbol=pos.symbol.upper(),
        instrument=instrument,
        signed_qty=float(pos.quantity),
        multiplier=multiplier,
        spot=spot,
        strike=pos.strike,
        rate=rate,
        sigma=sigma,
        t=t,
        position_id=pos.id or f"{pos.symbol.upper()}:{pos.strike}:{pos.expiry}",
    )


def wire_positions_to_domain(
    positions: Sequence[PortfolioPosition],
) -> list[DomainPosition]:
    """Bridge wire positions to domain ``Position`` objects (skips zero-qty)."""
    out: list[DomainPosition] = []
    for pos in positions:
        if pos.quantity == 0:
            continue
        out.append(DomainPosition.from_wire(pos))
    return out


# ── Provider RawChain -> per-contract OptionQuote + IVStats (§4.5) ────────────


def _moneyness(spot: float, strike: float) -> float:
    return spot / strike if strike else 0.0


def raw_contract_to_quote(
    contract: RawContract,
    *,
    spot: float,
    ofi: float,
    greeks: Greeks,
    wolfram: WolframComputation | None,
) -> OptionQuote:
    """Assemble a single wire ``OptionQuote`` from a raw contract + Greeks."""
    option_type = (
        OptionType.CALL if contract.option_type == "call" else OptionType.PUT
    )
    return OptionQuote(
        strike=contract.strike,
        type=option_type,
        expiry=contract.expiry,
        bid=contract.bid,
        ask=contract.ask,
        last_price=contract.last_price,
        volume=max(0, contract.volume),
        open_interest=max(0, contract.open_interest),
        iv=max(0.0, contract.implied_volatility),
        ofi=max(-1.0, min(1.0, ofi)),
        greeks=greeks,
        delta=greeks.delta,
        moneyness=_moneyness(spot, contract.strike),
        wolfram=wolfram,
    )


def _atm_iv(chain: RawChain) -> float:
    """The IV of the contract whose strike is closest to spot (0.0 if empty)."""
    contracts = list(chain.calls) + list(chain.puts)
    if not contracts:
        return 0.0
    closest = min(contracts, key=lambda c: abs(c.strike - chain.spot_price))
    return max(0.0, closest.implied_volatility)


def build_iv_stats(chain: RawChain) -> IVStats:
    """Derive ``IVStats`` from a single-expiry raw chain.

    With only one expiry's data, ``iv_rank`` / ``iv_percentile`` are computed
    from the cross-sectional IV distribution (where ATM IV sits within the
    chain's [min, max] band) — an honest single-snapshot proxy, not a fabricated
    52-week figure. ``term_structure`` is the single point we actually have.
    """
    contracts = list(chain.calls) + list(chain.puts)
    ivs = [c.implied_volatility for c in contracts if c.implied_volatility > 0.0]
    atm = _atm_iv(chain)
    if not ivs:
        return IVStats(
            iv_rank=0.0,
            iv_percentile=0.0,
            atm_iv=atm,
            iv_30d_high=atm,
            iv_30d_low=atm,
            term_structure=[(chain.expiry, atm)] if atm > 0 else [],
        )
    lo = min(ivs)
    hi = max(ivs)
    span = hi - lo
    rank = 0.0 if span <= 0 else max(0.0, min(1.0, (atm - lo) / span)) * 100.0
    below = sum(1 for v in ivs if v <= atm)
    percentile = (below / len(ivs)) * 100.0
    return IVStats(
        iv_rank=round(rank, 4),
        iv_percentile=round(percentile, 4),
        atm_iv=round(atm, 6),
        iv_30d_high=round(hi, 6),
        iv_30d_low=round(lo, 6),
        term_structure=[(chain.expiry, round(atm, 6))],
    )


def build_market_snapshot(
    chain: RawChain,
    *,
    quotes: list[OptionQuote],
    iv_stats: IVStats,
    data_source: str,
    near_expiry_filter_used: str,
    now: datetime | None = None,
) -> MarketSnapshot:
    """Assemble the canonical ``MarketSnapshot`` from raw + priced data (§4.5)."""
    ofi = compute_order_flow_imbalance(list(chain.calls), list(chain.puts))
    pin = compute_pin_risk_score(
        list(chain.calls), list(chain.puts), chain.spot_price
    )
    max_pain = compute_max_pain_strike(list(chain.calls), list(chain.puts))
    return MarketSnapshot(
        symbol=chain.symbol.upper(),
        spot_price=chain.spot_price,
        timestamp=chain.timestamp,
        expiry_used=chain.expiry,
        near_expiry_filter_used=near_expiry_filter_used,
        dte=dte_for_expiry(chain.expiry, now=now),
        order_flow_imbalance=max(-1.0, min(1.0, ofi)),
        pin_risk_score=max(0.0, min(1.0, pin)),
        max_pain_strike=max_pain,
        iv_stats=iv_stats,
        calls_count=len(chain.calls),
        puts_count=len(chain.puts),
        chain=quotes,
        data_source=data_source,
    )
