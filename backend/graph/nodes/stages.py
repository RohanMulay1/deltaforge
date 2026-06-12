"""Staged pipeline executor (ARCHITECTURE.md §5, §6, §8.2, WS2).

The canonical pipeline is a linear DAG:

    market_data -> greeks -> portfolio -> hedge -> scenario -> summary

Rather than run a LangGraph ``StateGraph`` twice (once for ``/analyze``, once
for the SSE stream), the stage logic lives in ONE async generator,
``run_pipeline_stages``, that yields a typed ``StageEvent`` after each stage.

  * ``run_analysis`` (pipeline.py) drains the generator and assembles the final
    ``AnalyzeResponse`` from the terminal state.
  * ``analysis_event_stream`` (pipeline.py) frames each ``StageEvent`` into an
    SSE event per §6.

A ``LangGraph`` ``StateGraph`` over the same node callables is ALSO compiled
(pipeline.py) for parity / introspection, but the streaming path uses this
generator because it must emit fine-grained per-stage SSE frames (including one
``wolfram`` frame per expression) which ``.astream()`` node-granularity cannot.

Wolfram failures NEVER raise out of a stage: the WolframService already degrades
to a labeled ``numeric_fallback`` DTO, so the engine status is honest and the
response still succeeds (§7). Only a market-data failure aborts the run.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.greeks_aggregation import WeightedLeg, aggregate_portfolio_greeks
from domain.hedging import HEDGE_TARGET_DELTA, delta_to_hedge
from errors import NoChainData, SymbolNotFound, UpstreamDataError
from models.schemas_common import OptionType, PipelineStage, WolframEngine
from models.schemas_greeks import Greeks
from models.schemas_hedge import HedgeRecommendation
from models.schemas_market import MarketSnapshot, OptionQuote
from models.schemas_portfolio import PortfolioGreeks, PortfolioPosition
from models.schemas_scenario import ScenarioAxis, ScenarioSurface
from models.schemas_wolfram import WolframComputation
from providers.base import RawChain, RawContract
from providers.errors import (
    NoChainDataError,
    ProviderUnavailable,
    SymbolNotFoundError,
    UpstreamDataError as ProviderUpstreamError,
)
from services.wolfram import WolframService
from services.wolfram.dto import (
    GreekInputs,
    HedgeLeg,
    HedgeRequest,
    PnLSurfaceInputs,
    Position as WolframPosition,
)

from graph.nodes import builders as B
from graph.state import GraphState, advance

logger = logging.getLogger(__name__)

# Cap how many chain contracts we price through the kernel per run. Pricing is
# the dominant cost; the ATM-nearest window is what the UI renders first.
MAX_PRICED_CONTRACTS = 60
# Default scenario grid when the caller does not POST /scenario explicitly.
_DEFAULT_SPOT_PCTS: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10)
_DEFAULT_IV_PCTS: tuple[float, ...] = (-0.05, 0.0, 0.05)
_GROQ_MODEL = "llama-3.3-70b-versatile"
_GROQ_MAX_TOKENS = 256
_GROQ_TEMPERATURE = 0.3


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _risk_free_rate() -> float:
    try:
        return float(os.environ.get("RISK_FREE_RATE", str(B.DEFAULT_RISK_FREE_RATE)))
    except ValueError:
        return B.DEFAULT_RISK_FREE_RATE


# ── Stage event envelope ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class StageEvent:
    """One emission from the staged pipeline.

    ``stage`` names the canonical stage. ``status`` is ``"start"`` or ``"done"``.
    ``payload`` carries the stage's wire model (``MarketSnapshot`` etc.) when
    ``status == "done"``; ``wolfram`` carries a single ``WolframComputation`` for
    a ``wolfram`` sub-event. ``state`` is the post-stage immutable snapshot.
    """

    stage: PipelineStage
    status: str  # "start" | "done"
    payload: object | None = None
    wolfram: WolframComputation | None = None
    state: GraphState = field(default_factory=dict)  # type: ignore[arg-type]


# ── market_data stage ─────────────────────────────────────────────────────────


def _select_expiry(expirations: Sequence[str], dte_max: int) -> str:
    """Pick the nearest expiry within ``dte_max`` days, else the nearest overall."""
    today = _now()
    dated = sorted(
        (e for e in expirations if e),
        key=lambda e: B.dte_for_expiry(e, now=today),
    )
    if not dated:
        raise NoChainData("no usable expirations returned by provider")
    within = [e for e in dated if 0 <= B.dte_for_expiry(e, now=today) <= dte_max]
    return within[0] if within else dated[0]


def _atm_window(contracts: Sequence[RawContract], spot: float, limit: int) -> list[RawContract]:
    """Return up to ``limit`` contracts nearest to spot (ATM-anchored)."""
    ordered = sorted(contracts, key=lambda c: abs(c.strike - spot))
    return ordered[:limit]


async def _fetch_chain(provider: object, symbol: str, dte_max: int) -> RawChain:
    """Fetch the nearest-expiry raw chain, mapping provider errors to domain."""
    try:
        expirations = await provider.get_expirations(symbol)  # type: ignore[attr-defined]
        expiry = _select_expiry(expirations, dte_max)
        return await provider.get_chain(symbol, expiry)  # type: ignore[attr-defined]
    except SymbolNotFoundError as exc:
        raise SymbolNotFound(str(exc), stage=PipelineStage.MARKET_DATA) from exc
    except NoChainDataError as exc:
        raise NoChainData(str(exc), stage=PipelineStage.MARKET_DATA) from exc
    except (ProviderUnavailable, ProviderUpstreamError) as exc:
        raise UpstreamDataError(str(exc), stage=PipelineStage.MARKET_DATA) from exc


# ── greeks stage: price each contract symbolically via the kernel ─────────────


async def _price_contract(
    service: WolframService,
    contract: RawContract,
    *,
    spot: float,
    rate: float,
) -> tuple[Greeks, WolframComputation]:
    """Symbolically price one contract; returns wire Greeks + provenance."""
    cp = 1 if contract.option_type == "call" else -1
    t = B.years_to_expiry(contract.expiry)
    sigma = max(contract.implied_volatility, 0.0)
    inputs = GreekInputs(
        spot=spot, strike=contract.strike, rate=rate, sigma=sigma, t=t, cp=cp
    )
    result = await service.contract_greeks(inputs)
    greeks = B.greeks_values_to_wire(result.greeks)
    comp = B.evaluation_to_computation(
        result.evaluation,
        inputs={
            "S": spot,
            "K": contract.strike,
            "r": rate,
            "sigma": sigma,
            "T": t,
            "cp": cp,
        },
        result_numeric=result.greeks.delta,
        label=f"Δ {contract.option_type} {contract.strike:g} (D[BS, S])",
    )
    return greeks, comp


# ── portfolio stage ───────────────────────────────────────────────────────────


async def _price_position(
    service: WolframService,
    pos: PortfolioPosition,
    *,
    spot: float,
    rate: float,
    chain_iv: float,
) -> tuple[str, WeightedLeg, WolframComputation]:
    """Price one portfolio leg; returns (position_id, weighted_leg, provenance)."""
    wl_pos: WolframPosition = B.wire_position_to_wolfram(
        pos, spot=spot, rate=rate, sigma=chain_iv
    )
    pid = wl_pos.position_id or pos.symbol.upper()
    weight = wl_pos.signed_qty * wl_pos.multiplier
    if wl_pos.is_equity:
        leg = WeightedLeg(
            position_id=pid,
            weight=weight,
            per_unit=Greeks(delta=1.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0),
        )
        # Equity needs no kernel call (degenerate case, §8.2). No provenance.
        comp = None  # type: ignore[assignment]
        return pid, leg, comp
    inputs = GreekInputs(
        spot=spot,
        strike=wl_pos.strike if wl_pos.strike is not None else spot,
        rate=rate,
        sigma=wl_pos.sigma if wl_pos.sigma is not None else chain_iv,
        t=wl_pos.t if wl_pos.t is not None else 0.0,
        cp=wl_pos.cp,
    )
    result = await service.contract_greeks(inputs)
    leg = WeightedLeg(
        position_id=pid,
        weight=weight,
        per_unit=B.greeks_values_to_wire(result.greeks),
    )
    comp = B.evaluation_to_computation(
        result.evaluation,
        inputs={
            "S": inputs.spot,
            "K": inputs.strike,
            "r": inputs.rate,
            "sigma": inputs.sigma,
            "T": inputs.t,
            "cp": inputs.cp,
        },
        result_numeric=result.greeks.delta,
        label=f"Leg Δ {pos.symbol} {pos.strike or ''} ({pos.instrument.value})",
    )
    return pid, leg, comp


def _empty_portfolio_greeks(spot: float) -> PortfolioGreeks:
    return PortfolioGreeks(
        delta=0.0,
        gamma=0.0,
        theta=0.0,
        vega=0.0,
        rho=0.0,
        net_delta_dollars=0.0,
        per_position={},
    )


# ── hedge stage ───────────────────────────────────────────────────────────────


def _hedge_legs_from_chain(
    quotes: Sequence[OptionQuote], spot: float
) -> list[HedgeLeg]:
    """Build candidate hedge legs from the priced chain (calls + puts nearest ATM)."""
    nearest = sorted(quotes, key=lambda q: abs(q.strike - spot))[:6]
    legs: list[HedgeLeg] = []
    for q in nearest:
        legs.append(
            HedgeLeg(
                label=f"{q.type.value} {q.strike:g}",
                delta=q.greeks.delta,
                option_type=q.type.value,
                strike=q.strike,
                expiry=q.expiry,
            )
        )
    return legs


def _empty_hedge(symbol: str, spot: float, computation: WolframComputation) -> HedgeRecommendation:
    """Honest no-exposure hedge (no fake 1-contract trade, §8.2)."""
    return HedgeRecommendation(
        symbol=symbol,
        delta_neutral_ratio=0.0,
        contracts_to_trade=0,
        option_type_to_trade=OptionType.CALL,
        strike_to_trade=spot,
        expiry_to_trade="",
        expected_pnl_range=(0.0, 0.0),
        current_portfolio_delta=0.0,
        residual_delta_after_hedge=0.0,
        delta_target=HEDGE_TARGET_DELTA,
        wolfram_computation_used=computation.expression,
        wolfram=computation,
        reasoning=(
            "No net delta exposure — portfolio is already delta-neutral or empty; "
            "no hedge required."
        ),
    )


# ── summary stage (Groq) ──────────────────────────────────────────────────────


def _build_summary_prompt(
    symbol: str,
    market: MarketSnapshot,
    greeks: PortfolioGreeks,
    hedge: HedgeRecommendation,
    engine: WolframEngine,
) -> str:
    return (
        f"Symbol: {symbol}\n"
        f"Spot price: ${market.spot_price:.2f}\n"
        f"Order flow imbalance: {market.order_flow_imbalance:+.4f} "
        f"(+1=all calls, -1=all puts)\n"
        f"Pin risk score: {market.pin_risk_score:.4f} (1.0=max pin risk)\n"
        f"Max pain strike: {market.max_pain_strike:g}\n"
        f"IV rank: {market.iv_stats.iv_rank:.1f}\n"
        f"Portfolio delta: {greeks.delta:.4f} "
        f"(net ${greeks.net_delta_dollars:,.0f}), "
        f"gamma {greeks.gamma:.4f}, theta {greeks.theta:.4f}/day, "
        f"vega {greeks.vega:.4f}\n"
        f"Hedge: trade {hedge.contracts_to_trade} "
        f"{hedge.option_type_to_trade.value.upper()} @ {hedge.strike_to_trade:g}, "
        f"residual delta {hedge.residual_delta_after_hedge:.4f} "
        f"(target {hedge.delta_target:.2f})\n"
        f"Compute engine: {engine.value}\n\n"
        "Write exactly 2 sentences summarizing the key risk and the recommended "
        "action for a derivatives trader. Be specific and quantitative."
    )


async def _generate_summary(prompt: str) -> str:
    """Call Groq for a 2-sentence narrative; degrade to a deterministic note."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_groq import ChatGroq
    except Exception as exc:  # noqa: BLE001 - missing dep must not break analysis
        logger.warning("langchain_groq unavailable: %s", exc)
        return "Risk summary unavailable (LLM client not installed)."

    def _invoke() -> str:
        llm = ChatGroq(
            model=_GROQ_MODEL,
            temperature=_GROQ_TEMPERATURE,
            max_tokens=_GROQ_MAX_TOKENS,
        )
        messages = [
            SystemMessage(
                content=(
                    "You are a senior derivatives risk analyst. Summarize options "
                    "risk data concisely for traders using precise financial "
                    "language. Never hedge with vague qualifiers."
                )
            ),
            HumanMessage(content=prompt),
        ]
        return str(llm.invoke(messages).content).strip()

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _invoke)
    except Exception as exc:  # noqa: BLE001 - Groq failure is non-fatal
        logger.error("Groq summary failed: %s", exc, exc_info=True)
        return "Risk summary temporarily unavailable; review the quantitative metrics above."


# ── The staged generator ──────────────────────────────────────────────────────


async def run_pipeline_stages(
    state: GraphState,
    *,
    service: WolframService,
    provider: object,
) -> AsyncIterator[StageEvent]:
    """Execute every stage, yielding a ``StageEvent`` as each completes.

    Raises a ``DeltaForgeError`` only on a fatal market-data failure; Wolfram and
    Groq failures degrade honestly and never abort the run.
    """
    symbol: str = state["symbol"]
    dte_max: int = state.get("dte_max", 7)
    rate = _risk_free_rate()
    provider_name = getattr(provider, "name", "yfinance")
    computations: list[WolframComputation] = []

    # ── 1. market_data ────────────────────────────────────────────────────────
    yield StageEvent(PipelineStage.MARKET_DATA, "start", state=state)
    chain = await _fetch_chain(provider, symbol, dte_max)
    iv_stats = B.build_iv_stats(chain)

    # ── 2. greeks (price the ATM window of the chain) ─────────────────────────
    yield StageEvent(PipelineStage.GREEKS, "start", state=state)
    spot = chain.spot_price
    # Per-quote ``ofi`` mirrors the chain-level imbalance (computed once here and
    # again inside build_market_snapshot for the snapshot scalar).
    from analytics import compute_order_flow_imbalance

    ofi = max(
        -1.0,
        min(1.0, compute_order_flow_imbalance(list(chain.calls), list(chain.puts))),
    )

    priced_calls = _atm_window(chain.calls, spot, MAX_PRICED_CONTRACTS // 2)
    priced_puts = _atm_window(chain.puts, spot, MAX_PRICED_CONTRACTS // 2)
    priced_set = {id(c) for c in priced_calls} | {id(c) for c in priced_puts}

    quotes: list[OptionQuote] = []
    for contract in list(chain.calls) + list(chain.puts):
        if id(contract) in priced_set:
            greeks, comp = await _price_contract(service, contract, spot=spot, rate=rate)
            computations.append(comp)
            yield StageEvent(PipelineStage.GREEKS, "wolfram", wolfram=comp, state=state)
            wolfram = comp
        else:
            # Outside the priced window: surface raw row with zero Greeks (UI
            # virtualizes; these settle if the user scrolls/expands later).
            greeks = Greeks(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)
            wolfram = None
        quotes.append(
            B.raw_contract_to_quote(
                contract, spot=spot, ofi=ofi, greeks=greeks, wolfram=wolfram
            )
        )

    market = B.build_market_snapshot(
        chain,
        quotes=quotes,
        iv_stats=iv_stats,
        data_source=provider_name,
        near_expiry_filter_used=f"<= {dte_max} dte",
    )
    state = advance(state, market=market, wolfram_computations=list(computations))
    yield StageEvent(PipelineStage.MARKET_DATA, "done", payload=market, state=state)
    yield StageEvent(PipelineStage.GREEKS, "done", payload=market, state=state)
    yield StageEvent(PipelineStage.IV_SURFACE, "done", payload=iv_stats, state=state)

    # ── 3. portfolio ──────────────────────────────────────────────────────────
    yield StageEvent(PipelineStage.PORTFOLIO, "start", state=state)
    positions: list[PortfolioPosition] = state.get("positions") or []
    atm_iv = iv_stats.atm_iv if iv_stats.atm_iv > 0 else 0.0
    if positions:
        legs: list[WeightedLeg] = []
        for pos in positions:
            pid, leg, comp = await _price_position(
                service, pos, spot=spot, rate=rate, chain_iv=atm_iv
            )
            legs.append(leg)
            if comp is not None:
                computations.append(comp)
                yield StageEvent(
                    PipelineStage.PORTFOLIO, "wolfram", wolfram=comp, state=state
                )
        portfolio_greeks = aggregate_portfolio_greeks(legs, spot)
    else:
        portfolio_greeks = _empty_portfolio_greeks(spot)

    state = advance(
        state,
        portfolio_greeks=portfolio_greeks,
        wolfram_computations=list(computations),
    )
    yield StageEvent(
        PipelineStage.PORTFOLIO, "done", payload=portfolio_greeks, state=state
    )

    # ── 4. hedge ──────────────────────────────────────────────────────────────
    yield StageEvent(PipelineStage.HEDGE, "start", state=state)
    net_delta = portfolio_greeks.delta
    target = HEDGE_TARGET_DELTA
    if abs(net_delta) <= 1e-9 or not positions:
        # Honest no-exposure path still records the (degenerate) WL string.
        legs_for_hedge = _hedge_legs_from_chain(quotes, spot)
        hedge_req = HedgeRequest(
            symbol=symbol,
            current_delta=net_delta,
            delta_target=target,
            legs=tuple(legs_for_hedge),
            spot=spot,
            rate=rate,
        )
        hedge_result = await service.delta_neutral_hedge(hedge_req)
        comp = B.evaluation_to_computation(
            hedge_result.evaluation,
            inputs={"current_delta": net_delta, "delta_target": target},
            result_numeric=hedge_result.residual_delta,
        )
        computations.append(comp)
        yield StageEvent(PipelineStage.HEDGE, "wolfram", wolfram=comp, state=state)
        hedge = _empty_hedge(symbol, spot, comp)
    else:
        legs_for_hedge = _hedge_legs_from_chain(quotes, spot)
        hedge_req = HedgeRequest(
            symbol=symbol,
            current_delta=net_delta,
            delta_target=target,
            legs=tuple(legs_for_hedge),
            spot=spot,
            rate=rate,
        )
        hedge_result = await service.delta_neutral_hedge(hedge_req)
        comp = B.evaluation_to_computation(
            hedge_result.evaluation,
            inputs={
                "current_delta": net_delta,
                "delta_target": target,
                "delta_to_hedge": delta_to_hedge(net_delta, delta_target=target),
            },
            result_numeric=hedge_result.residual_delta,
        )
        computations.append(comp)
        yield StageEvent(PipelineStage.HEDGE, "wolfram", wolfram=comp, state=state)
        hedge = _assemble_hedge(
            symbol=symbol,
            spot=spot,
            legs=legs_for_hedge,
            quantities=hedge_result.hedge_quantities,
            residual=hedge_result.residual_delta,
            net_delta=net_delta,
            target=target,
            computation=comp,
        )

    state = advance(state, hedge=hedge, wolfram_computations=list(computations))
    yield StageEvent(PipelineStage.HEDGE, "done", payload=hedge, state=state)

    # ── 5. scenario ───────────────────────────────────────────────────────────
    yield StageEvent(PipelineStage.SCENARIO, "start", state=state)
    scenario, scenario_comp = await _build_scenario(
        service,
        symbol=symbol,
        spot=spot,
        rate=rate,
        positions=positions,
        chain_iv=atm_iv,
        spot_pcts=_DEFAULT_SPOT_PCTS,
        iv_pcts=_DEFAULT_IV_PCTS,
    )
    if scenario_comp is not None:
        computations.append(scenario_comp)
        yield StageEvent(
            PipelineStage.SCENARIO, "wolfram", wolfram=scenario_comp, state=state
        )
    state = advance(state, scenario=scenario, wolfram_computations=list(computations))
    yield StageEvent(PipelineStage.SCENARIO, "done", payload=scenario, state=state)

    # ── 6. summary (Groq) ─────────────────────────────────────────────────────
    yield StageEvent(PipelineStage.SUMMARY, "start", state=state)
    engine_status = B.engine_status_to_wire(await service.health())
    summary = await _generate_summary(
        _build_summary_prompt(
            symbol, market, portfolio_greeks, hedge, engine_status.engine_in_use
        )
    )
    legacy_wl = hedge.wolfram_computation_used or (
        computations[0].expression if computations else ""
    )
    state = advance(
        state,
        risk_summary=summary,
        engine_status=engine_status,
        wolfram_computations=list(computations),
        wolfram_computation_used=legacy_wl,
    )
    yield StageEvent(PipelineStage.SUMMARY, "done", payload=summary, state=state)


# ── hedge / scenario assembly helpers ─────────────────────────────────────────


def _assemble_hedge(
    *,
    symbol: str,
    spot: float,
    legs: Sequence[HedgeLeg],
    quantities: Sequence[float],
    residual: float,
    net_delta: float,
    target: float,
    computation: WolframComputation,
) -> HedgeRecommendation:
    """Pick the dominant hedge leg for the single-instrument UI summary."""
    if not legs or not quantities:
        return _empty_hedge(symbol, spot, computation)
    idx = max(range(len(quantities)), key=lambda i: abs(quantities[i]))
    leg = legs[idx]
    contracts = int(round(quantities[idx]))
    option_type = OptionType.CALL if leg.option_type == "call" else OptionType.PUT
    ratio = (target - net_delta) / leg.delta if leg.delta else 0.0
    pnl_band = abs(net_delta) * spot * 0.01
    return HedgeRecommendation(
        symbol=symbol,
        delta_neutral_ratio=ratio,
        contracts_to_trade=contracts,
        option_type_to_trade=option_type,
        strike_to_trade=leg.strike,
        expiry_to_trade=leg.expiry,
        expected_pnl_range=(-pnl_band, pnl_band),
        current_portfolio_delta=net_delta,
        residual_delta_after_hedge=residual,
        delta_target=target,
        wolfram_computation_used=computation.expression,
        wolfram=computation,
        reasoning=(
            f"Net delta {net_delta:+.2f} vs target {target:.2f}. NMinimize selects "
            f"{contracts} {option_type.value} @ {leg.strike:g} (Δ {leg.delta:+.3f}); "
            f"residual {residual:+.3f}."
        ),
    )


async def _build_scenario(
    service: WolframService,
    *,
    symbol: str,
    spot: float,
    rate: float,
    positions: Sequence[PortfolioPosition],
    chain_iv: float,
    spot_pcts: tuple[float, ...],
    iv_pcts: tuple[float, ...],
) -> tuple[ScenarioSurface, Optional[WolframComputation]]:
    """Build a real Wolfram P&L surface, or an honest ``is_stub`` surface.

    With no positions there is nothing to revalue, so we return a stub surface
    (``is_stub=True``) carrying a degenerate (but real) WL expression so the UI
    still has an explainable provenance object (§4.8).
    """
    x_axis = ScenarioAxis(name="spot_pct", values=[v * 100.0 for v in spot_pcts])
    y_axis = ScenarioAxis(name="iv_pct", values=[v * 100.0 for v in iv_pcts])

    wl_positions = [
        B.wire_position_to_wolfram(p, spot=spot, rate=rate, sigma=chain_iv)
        for p in positions
    ]
    inputs = PnLSurfaceInputs(
        symbol=symbol,
        spot=spot,
        rate=rate,
        legs=tuple(wl_positions),
        spot_pcts=spot_pcts,
        iv_pcts=iv_pcts,
    )
    result = await service.pnl_surface(inputs)
    comp = B.evaluation_to_computation(
        result.evaluation,
        inputs={"spot": spot, "rate": rate, "n_legs": float(len(wl_positions))},
        result_numeric=result.base_pnl,
        label="Scenario P&L surface (symbolic pnl[S, σ, T])",
    )
    grid = [list(row) for row in result.pnl_grid]
    if not grid:
        grid = [[0.0 for _ in spot_pcts] for _ in iv_pcts]
    breakeven = _breakeven_spot(spot, spot_pcts, grid)
    surface = ScenarioSurface(
        x_axis=x_axis,
        y_axis=y_axis,
        pnl_grid=grid,
        base_pnl=result.base_pnl,
        breakeven_spot=breakeven,
        wolfram=comp,
        is_stub=not bool(positions),
    )
    return surface, comp


def _breakeven_spot(
    spot: float, spot_pcts: Sequence[float], grid: Sequence[Sequence[float]]
) -> float | None:
    """Find the spot at which the middle-IV P&L row crosses zero (linear interp)."""
    if not grid:
        return None
    row = grid[len(grid) // 2]
    if len(row) != len(spot_pcts):
        return None
    for i in range(len(row) - 1):
        a, b = row[i], row[i + 1]
        if a == 0.0:
            return spot * (1.0 + spot_pcts[i])
        if (a < 0.0) != (b < 0.0):
            frac = a / (a - b) if (a - b) != 0 else 0.0
            pct = spot_pcts[i] + frac * (spot_pcts[i + 1] - spot_pcts[i])
            return spot * (1.0 + pct)
    return None
