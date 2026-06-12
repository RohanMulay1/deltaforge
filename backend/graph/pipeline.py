"""DeltaForge analysis pipeline — canonical entrypoints (WS2).

This module exposes the two entrypoints WS4 / the routers import:

  * ``run_analysis(req, *, service, provider, sessionmaker=None) -> AnalyzeResponse``
    — runs every stage and assembles the full canonical ``AnalyzeResponse``
      (§4.10), persisting one ``SavedAnalysis`` when a DB session is available.

  * ``analysis_event_stream(req, *, service, provider, sessionmaker=None)
        -> AsyncIterator[bytes]`` — the SSE byte stream (§6): one frame per stage
      transition + per Wolfram expression, a 15s heartbeat, and a terminal
      ``done`` frame whose payload equals ``run_analysis``.

Both consume the SAME staged generator (``graph.nodes.stages``), so the streamed
``done`` payload is byte-for-byte the non-stream ``/analyze`` result.

A LangGraph ``StateGraph`` over the canonical node names is ALSO compiled
(``deltaforge_graph``) for parity / introspection; the request paths above use
the generator because SSE needs finer-grained (per-expression) emissions than
node-level ``.astream()`` provides.

Wolfram failures degrade to ``numeric_fallback`` WITHOUT a 500 (the service
already returns labeled fallback DTOs); only a fatal market-data error raises.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timezone
from decimal import Decimal

from errors import DeltaForgeError, ERROR_INTERNAL, ErrorEnvelope
from models.schemas_analyze import AnalyzeResponse
from models.schemas_common import PipelineStage
from models.schemas_greeks import Greeks
from models.schemas_portfolio import PortfolioGreeks, PortfolioPosition
from models.schemas_requests import AnalyzeRequest
from services.wolfram import WolframService
from services.wolfram.dto import GreekInputs

from domain.greeks_aggregation import WeightedLeg, aggregate_portfolio_greeks
from graph.nodes import builders as B
from graph.nodes import stages as S
from graph.nodes.stages import StageEvent, run_pipeline_stages
from graph.state import GraphState, seed_state
import sse

logger = logging.getLogger(__name__)

# Map a completed PipelineStage to the SSE *payload* event name (§6 table).
_STAGE_PAYLOAD_EVENT: dict[PipelineStage, str] = {
    PipelineStage.MARKET_DATA: sse.EVENT_MARKET,
    PipelineStage.PORTFOLIO: sse.EVENT_PORTFOLIO,
    PipelineStage.HEDGE: sse.EVENT_HEDGE,
    PipelineStage.SCENARIO: sse.EVENT_SCENARIO,
    PipelineStage.SUMMARY: sse.EVENT_SUMMARY,
}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── Final AnalyzeResponse assembly (§4.10) ────────────────────────────────────


def assemble_response(state: GraphState) -> AnalyzeResponse:
    """Assemble the full canonical ``AnalyzeResponse`` from a terminal state.

    Raises ``RuntimeError`` if a required stage output is missing — the staged
    generator always fills these on a successful run.
    """
    market = state.get("market")
    portfolio_greeks = state.get("portfolio_greeks")
    hedge = state.get("hedge")
    scenario = state.get("scenario")
    engine_status = state.get("engine_status")
    if market is None or portfolio_greeks is None or hedge is None:
        raise RuntimeError("pipeline produced an incomplete state")
    if scenario is None or engine_status is None:
        raise RuntimeError("pipeline produced an incomplete state (scenario/engine)")

    return AnalyzeResponse(
        symbol=market.symbol,
        spot_price=market.spot_price,
        expiry=market.expiry_used,
        calls_count=market.calls_count,
        puts_count=market.puts_count,
        order_flow_imbalance=market.order_flow_imbalance,
        pin_risk_score=market.pin_risk_score,
        iv_rank=market.iv_stats.iv_rank,
        market=market,
        options_chain=list(market.chain),
        portfolio_greeks=portfolio_greeks,
        hedge=hedge,
        scenario=scenario,
        risk_summary=state.get("risk_summary") or "",
        wolfram_computation_used=state.get("wolfram_computation_used") or "",
        wolfram_computations=list(state.get("wolfram_computations") or []),
        engine_status=engine_status,
        analysis_id=None,
        generated_at=_now(),
    )


# ── Persistence (one SavedAnalysis per /analyze, best-effort) ─────────────────


async def _persist_analysis(
    response: AnalyzeResponse,
    dte_max: int,
    sessionmaker: object | None,
) -> str | None:
    """Persist one ``SavedAnalysis``; on any DB error, log and continue (§9.3).

    Returns the new ``analysis_id`` (str UUID) when persisted, else ``None``. A
    DB outage must NEVER fail the analysis — the response still returns.
    """
    if sessionmaker is None:
        return None
    try:
        from db.models.saved_analysis import SavedAnalysis
        from db.repositories.analysis_repo import SavedAnalysisRepository
    except Exception as exc:  # noqa: BLE001 - persistence is optional
        logger.warning("Persistence layer unavailable: %s", exc)
        return None

    engine_mode = response.engine_status.engine_in_use.value
    wolfram_expressions = [c.expression for c in response.wolfram_computations]
    wolfram_inputs = {
        c.label: c.inputs for c in response.wolfram_computations if c.inputs
    }
    wolfram_raw = {
        c.label: c.result_raw
        for c in response.wolfram_computations
        if c.result_raw is not None
    }

    try:
        session = sessionmaker()
        async with session as s:  # type: ignore[union-attr]
            repo = SavedAnalysisRepository(s)
            row = SavedAnalysis(
                portfolio_id=None,
                symbol=response.symbol,
                dte_max=dte_max,
                spot_price=Decimal(str(response.spot_price)),
                expiry_used=response.expiry,
                order_flow_imbalance=Decimal(str(response.order_flow_imbalance)),
                pin_risk_score=Decimal(str(response.pin_risk_score)),
                engine_mode=engine_mode,
                wolfram_inputs=wolfram_inputs or None,
                wolfram_expressions=wolfram_expressions or None,
                wolfram_raw_result=wolfram_raw or None,
                wolfram_computation_used=response.wolfram_computation_used or None,
                portfolio_greeks=response.portfolio_greeks.model_dump(mode="json"),
                hedge_recommendation=response.hedge.model_dump(mode="json"),
                full_response=response.model_dump(mode="json"),
                risk_summary=response.risk_summary or None,
                groq_model=S._GROQ_MODEL,
            )
            await repo.add(row)
            await s.commit()
            return str(row.id)
    except Exception as exc:  # noqa: BLE001 - DB down must not fail analysis
        logger.error("Failed to persist SavedAnalysis: %s", exc, exc_info=True)
        return None


# ── run_analysis — non-streaming canonical entrypoint ─────────────────────────


async def run_analysis(
    req: AnalyzeRequest,
    *,
    service: WolframService,
    provider: object,
    sessionmaker: object | None = None,
) -> AnalyzeResponse:
    """Run the full pipeline and return the canonical ``AnalyzeResponse`` (§4.10).

    Persists one ``SavedAnalysis`` when ``sessionmaker`` is provided and the DB
    is reachable; a DB failure is logged and swallowed (the analysis returns).
    """
    state = seed_state(req.symbol, req.dte_max, req.positions)
    async for event in run_pipeline_stages(state, service=service, provider=provider):
        if event.status == "done":
            state = event.state

    response = assemble_response(state)
    analysis_id = await _persist_analysis(response, req.dte_max, sessionmaker)
    if analysis_id is not None:
        response = response.model_copy(update={"analysis_id": analysis_id})
    return response


# ── analysis_event_stream — SSE byte stream (§6) ──────────────────────────────


async def analysis_event_stream(
    req: AnalyzeRequest,
    *,
    service: WolframService,
    provider: object,
    sessionmaker: object | None = None,
) -> AsyncIterator[bytes]:
    """Yield SSE frames for the §6 event sequence with a 15s heartbeat.

    The terminal ``done`` frame carries the SAME ``AnalyzeResponse`` that
    ``run_analysis`` returns. Any fatal error is emitted as a single ``error``
    frame (``ErrorEnvelope``) and the stream ends.
    """
    seq = 0
    state = seed_state(req.symbol, req.dte_max, req.positions)

    # Run the staged generator on a queue so a heartbeat can interleave during
    # slow stages (kernel pricing / Groq) without blocking frame emission.
    queue: asyncio.Queue[StageEvent | Exception | None] = asyncio.Queue()

    async def _produce() -> None:
        try:
            async for event in run_pipeline_stages(
                state, service=service, provider=provider
            ):
                await queue.put(event)
        except Exception as exc:  # noqa: BLE001 - surfaced as an error frame
            await queue.put(exc)
        finally:
            await queue.put(None)

    producer = asyncio.create_task(_produce())
    terminal_state: GraphState = state
    engine_emitted = False

    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    queue.get(), timeout=sse.HEARTBEAT_INTERVAL_S
                )
            except asyncio.TimeoutError:
                yield sse.heartbeat()
                continue

            if item is None:
                break
            if isinstance(item, Exception):
                yield _error_frame(item, seq)
                seq += 1
                break

            for event_name, data in _frames_for_event(item):
                yield sse.frame(event_name, data, seq=seq)
                seq += 1
            # Emit the engine frame once, right after the summary payload, so the
            # status pill resolves honestly near the end of the stream (§6 row 11).
            if (
                item.stage is PipelineStage.SUMMARY
                and item.status == "done"
                and not engine_emitted
                and item.state.get("engine_status") is not None
            ):
                yield sse.frame(
                    sse.EVENT_ENGINE, item.state["engine_status"], seq=seq
                )
                seq += 1
                engine_emitted = True
            if item.status == "done":
                terminal_state = item.state

        # Terminal reconcile: emit the authoritative ``done`` AnalyzeResponse.
        try:
            response = assemble_response(terminal_state)
            analysis_id = await _persist_analysis(response, req.dte_max, sessionmaker)
            if analysis_id is not None:
                response = response.model_copy(update={"analysis_id": analysis_id})
            yield sse.frame(sse.EVENT_DONE, response, seq=seq)
            seq += 1
        except Exception as exc:  # noqa: BLE001 - assembly failure -> error frame
            logger.error("Stream assembly failed: %s", exc, exc_info=True)
            yield _error_frame(exc, seq)
    finally:
        producer.cancel()
        try:
            await producer
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


def _frames_for_event(event: StageEvent) -> list[tuple[str, object]]:
    """Return the ordered ``(event_name, data)`` frames for a ``StageEvent``.

    A ``wolfram`` sub-event emits exactly one ``wolfram`` frame. A ``start`` or
    ``done`` transition emits a ``stage`` frame; a ``done`` ALSO emits the
    stage's payload frame (``market``/``portfolio``/``hedge``/``scenario``/
    ``summary``) and, for ``iv_surface``, the ``iv_surface`` stage marker.
    """
    if event.status == "wolfram" and event.wolfram is not None:
        return [(sse.EVENT_WOLFRAM, event.wolfram)]

    frames: list[tuple[str, object]] = [
        (sse.EVENT_STAGE, {"stage": event.stage.value, "status": event.status})
    ]
    if event.status == "done":
        payload_event = _STAGE_PAYLOAD_EVENT.get(event.stage)
        if payload_event and event.payload is not None:
            frames.append((payload_event, _payload_data(event)))
    return frames


def _payload_data(event: StageEvent) -> object:
    """Coerce a stage payload into its SSE data shape."""
    if event.stage is PipelineStage.SUMMARY:
        return {"risk_summary": event.payload}
    return event.payload


def _error_frame(exc: Exception, seq: int) -> bytes:
    """Build an ``error`` SSE frame from an exception (§6 / §7)."""
    if isinstance(exc, DeltaForgeError):
        error_code = exc.error_code
        detail = exc.detail
        stage = exc.stage
    else:
        error_code = ERROR_INTERNAL
        detail = "An internal error occurred while streaming the analysis."
        stage = None
    envelope = ErrorEnvelope(
        error=error_code,
        detail=detail,
        stage=stage,
        field_errors=None,
        request_id="stream",
        timestamp=_now(),
    )
    return sse.frame(sse.EVENT_ERROR, envelope, seq=seq)


# ── /portfolio/greeks — debounced aggregate (no full pipeline) ────────────────


async def aggregate_position_greeks(
    positions: Sequence[PortfolioPosition],
    *,
    symbol: str,
    spot: float,
    service: WolframService,
    chain_iv: float = 0.0,
) -> PortfolioGreeks:
    """Aggregate Greeks for posted positions without running the full pipeline.

    Each option leg is priced symbolically via the kernel (honest fallback when
    unavailable); equity is the degenerate delta=1 case. Used by the rail's
    debounced ``POST /portfolio/greeks`` endpoint (§3).
    """
    rate = S._risk_free_rate()
    legs: list[WeightedLeg] = []
    for pos in positions:
        if pos.quantity == 0:
            continue
        wl_pos = B.wire_position_to_wolfram(
            pos, spot=spot, rate=rate, sigma=chain_iv or None
        )
        pid = wl_pos.position_id or pos.symbol.upper()
        weight = wl_pos.signed_qty * wl_pos.multiplier
        if wl_pos.is_equity:
            legs.append(
                WeightedLeg(
                    position_id=pid,
                    weight=weight,
                    per_unit=Greeks(
                        delta=1.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0
                    ),
                )
            )
            continue
        inputs = GreekInputs(
            spot=spot,
            strike=wl_pos.strike if wl_pos.strike is not None else spot,
            rate=rate,
            sigma=wl_pos.sigma if wl_pos.sigma is not None else (chain_iv or 0.2),
            t=wl_pos.t if wl_pos.t is not None else 0.0,
            cp=wl_pos.cp,
        )
        result = await service.contract_greeks(inputs)
        legs.append(
            WeightedLeg(
                position_id=pid,
                weight=weight,
                per_unit=B.greeks_values_to_wire(result.greeks),
            )
        )
    return aggregate_portfolio_greeks(legs, spot)


# ── LangGraph parity graph (introspection; request paths use the generator) ───


def _build_graph():  # type: ignore[no-untyped-def]
    """Compile a LangGraph over the canonical node names for parity.

    The nodes are thin sync shims that record the stage was visited; the real
    work runs in the async staged generator. This graph exists so the canonical
    DAG shape (market_data -> greeks -> portfolio -> hedge -> scenario ->
    summary) is introspectable and tooling that imports a compiled graph keeps
    working. It is NOT used by the HTTP request paths.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception as exc:  # noqa: BLE001 - graph is optional tooling
        logger.warning("langgraph unavailable; skipping parity graph: %s", exc)
        return None

    def _passthrough(state: GraphState) -> GraphState:
        return state

    graph = StateGraph(GraphState)
    node_order = [
        "market_data",
        "greeks",
        "portfolio",
        "hedge",
        "scenario",
        "summary",
    ]
    for name in node_order:
        graph.add_node(name, _passthrough)
    graph.add_edge(START, node_order[0])
    for a, b in zip(node_order, node_order[1:]):
        graph.add_edge(a, b)
    graph.add_edge(node_order[-1], END)
    return graph.compile()


deltaforge_graph = _build_graph()
