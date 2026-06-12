"""Server-Sent Events framing helpers (ARCHITECTURE.md §6).

``GET /analyze/stream`` returns ``text/event-stream``. The wire framing is:

    event: <name>\\n
    id: <seq>\\n
    data: <json>\\n
    \\n

with a comment heartbeat ``: keepalive\\n\\n`` every 15s to keep proxies from
closing an idle connection. The client closes on ``done`` / ``error``.

────────────────────────────────────────────────────────────────────────────
REDUCER CONTRACT (frontend ``useAnalysisStream`` must obey this)
────────────────────────────────────────────────────────────────────────────
The stream emits the §6 event sequence. Each event NAME maps to a slice of the
single accumulated ``AnalysisResult``:

  * ``stage``    -> ``stages[payload.stage] = payload.status`` (panel 4-state)
  * ``market``   -> set ``market`` + ``options_chain`` + HUD scalars
  * ``portfolio``-> set ``portfolio_greeks``
  * ``iv_surface`` (stage event) -> IV surface ready
  * ``wolfram``  -> APPEND to ``wolfram_computations`` (repeats; one per expr)
  * ``hedge``    -> set ``hedge``
  * ``scenario`` -> set ``scenario``
  * ``summary``  -> set ``risk_summary``
  * ``engine``   -> set ``engine_status``
  * ``done``     -> AUTHORITATIVE full ``AnalyzeResponse``; reconcile + stop
  * ``error``    -> ``ErrorEnvelope``; toast + stop spinners

Events are OUT-OF-ORDER SAFE: a reducer keyed by event name must never assume
ordering. ``done`` is the single source of truth and overwrites any partial
state. ``id`` is a monotonically increasing sequence for client de-duplication.
"""

from __future__ import annotations

import json
from typing import Any

# Heartbeat cadence (§6): emit a comment frame every 15s of idle.
HEARTBEAT_INTERVAL_S = 15.0

# Canonical SSE event names (§6 table). The frontend reduces by these strings.
EVENT_STAGE = "stage"
EVENT_MARKET = "market"
EVENT_PORTFOLIO = "portfolio"
EVENT_IV_SURFACE = "iv_surface"
EVENT_HEDGE = "hedge"
EVENT_WOLFRAM = "wolfram"
EVENT_SCENARIO = "scenario"
EVENT_SUMMARY = "summary"
EVENT_ENGINE = "engine"
EVENT_DONE = "done"
EVENT_ERROR = "error"


def _json(payload: Any) -> str:
    """Serialize a payload to compact JSON.

    Pydantic models are serialized via ``model_dump(mode="json")`` so datetimes
    and enums become wire-safe primitives. Plain dicts/lists pass through.
    """
    if hasattr(payload, "model_dump"):
        data = payload.model_dump(mode="json")
    else:
        data = payload
    return json.dumps(data, separators=(",", ":"), default=str)


def frame(event: str, data: Any, *, seq: int | None = None) -> bytes:
    """Build one SSE frame: ``event:``/``id:``/``data:`` + blank-line terminator.

    Multi-line JSON is split across ``data:`` lines per the SSE spec (each line
    of the payload gets its own ``data:`` prefix).
    """
    lines: list[str] = [f"event: {event}"]
    if seq is not None:
        lines.append(f"id: {seq}")
    payload = _json(data)
    for line in payload.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")  # terminating blank line -> frame boundary
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def heartbeat() -> bytes:
    """Build a comment heartbeat frame (keeps idle connections open, §6)."""
    return b": keepalive\n\n"
