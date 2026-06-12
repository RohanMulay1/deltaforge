"""Extra router coverage: scenario, trade-ticket, and the SSE stream path.

All use the ``test_client`` fixture (fake Wolfram in numeric_fallback, fake
market provider, no DB) so no kernel / network / Postgres is touched. The SSE
test drives the full pipeline (market_data -> greeks -> portfolio -> hedge ->
scenario -> summary) through ``analysis_event_stream`` + the SSE framing.
"""

from __future__ import annotations


# ── POST /scenario ────────────────────────────────────────────────────────────


def test_scenario_returns_pnl_grid(test_client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "positions": [
            {
                "symbol": "SPY",
                "instrument": "call",
                "strike": 530.0,
                "expiry": "2027-01-15",
                "quantity": 5,
            }
        ],
        "spot_pct_range": [-0.1, 0.1, 0.05],
        "iv_pct_range": [-0.2, 0.2, 0.1],
    }
    resp = test_client.post("/scenario", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    grid = body["pnl_grid"]
    assert len(grid) >= 1 and len(grid[0]) >= 1
    assert "base_pnl" in body
    # The fake service is forced to numeric_fallback — labeled honestly.
    assert body["wolfram"]["engine"] == "numeric_fallback"


def test_scenario_rejects_bad_range(test_client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "positions": [{"symbol": "SPY", "instrument": "equity", "quantity": 10}],
        "spot_pct_range": [-0.1, 0.1],  # too few elements (needs lo, hi, step)
        "iv_pct_range": [-0.2, 0.2, 0.1],
    }
    resp = test_client.post("/scenario", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"


# ── POST /trade-ticket ────────────────────────────────────────────────────────


def test_trade_ticket_exports_paper_blob(test_client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "symbol": "SPY",
        "legs": [
            {
                "symbol": "SPY",
                "action": "buy",
                "quantity": 2,
                "instrument": "call",
                "strike": 530.0,
                "expiry": "2027-01-15",
            }
        ],
        "note": "delta hedge",
    }
    resp = test_client.post("/trade-ticket", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "paper_export"
    assert body["ticket_id"]
    assert "BUY" in body["blob"].upper()
    # Compliance: export only, never executes — disclaimer is always present.
    assert body["disclaimer"]


def test_trade_ticket_requires_a_leg(test_client) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.post("/trade-ticket", json={"symbol": "SPY", "legs": []})
    assert resp.status_code == 422


# ── GET /analyze/stream (SSE) — drives the whole pipeline ─────────────────────


def test_analyze_stream_emits_events_and_done(test_client, fake_groq) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.get("/analyze/stream?symbol=SPY&dte_max=7")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    text = resp.text
    # Canonical stage/event names per §6 must appear, terminating in `done`.
    assert "event: market" in text
    assert "event: hedge" in text
    assert "event: done" in text
    # The summary node used the patched deterministic Groq narrative.
    assert "event: summary" in text
