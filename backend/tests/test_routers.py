"""Router / TestClient integration tests (ARCHITECTURE.md §3, §7).

All external systems are mocked via the ``test_client`` fixture (fake Wolfram in
forced numeric_fallback, fake market provider, no DB). Covers:

  * GET  /health                 → 200 HealthResponse
  * GET  /health/wolfram         → EngineStatus reflecting numeric_fallback
  * POST /portfolio/greeks       → aggregate PortfolioGreeks
  * POST /analyze                → full AnalyzeResponse (no zeros where priced)
  * error envelope on bad input  → 422 validation_error
  * unknown symbol               → 404 not_found envelope
"""

from __future__ import annotations

import pytest


def test_health_ok(test_client) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_health_wolfram_reports_fallback(test_client) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.get("/health/wolfram")
    assert resp.status_code == 200
    body = resp.json()
    # The fake service is forced into numeric_fallback.
    assert body["engine_in_use"] == "numeric_fallback"
    assert body["wolfram_available"] is False
    assert body["reason"]


def test_portfolio_greeks_aggregates(test_client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "symbol": "SPY",
        "positions": [
            {
                "symbol": "SPY",
                "instrument": "call",
                "strike": 530.0,
                "expiry": "2027-01-15",
                "quantity": 5,
            }
        ],
        "spot_price": 530.0,
    }
    resp = test_client.post("/portfolio/greeks", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    # 5 long ATM calls -> a clearly positive net delta (not the all-zero mock).
    assert body["delta"] > 0.0
    assert "net_delta_dollars" in body


def test_portfolio_greeks_empty_positions(test_client) -> None:  # type: ignore[no-untyped-def]
    payload = {"symbol": "SPY", "positions": [], "spot_price": 530.0}
    resp = test_client.post("/portfolio/greeks", json=payload)
    assert resp.status_code == 200
    assert resp.json()["delta"] == 0.0


def test_portfolio_greeks_unknown_symbol_without_spot_404(test_client) -> None:  # type: ignore[no-untyped-def]
    # No spot_price override -> provider lookup -> unknown symbol -> 404 envelope.
    payload = {"symbol": "ZZZ", "positions": []}
    resp = test_client.post("/portfolio/greeks", json=payload)
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_found"
    assert "request_id" in body


@pytest.mark.usefixtures("fake_groq")
def test_analyze_happy_path(test_client) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.post("/analyze", json={"symbol": "SPY", "dte_max": 365})
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "SPY"
    assert body["spot_price"] == 530.0
    assert body["calls_count"] == 5
    assert body["puts_count"] == 5
    # Chain is populated and priced (greeks present per quote).
    assert len(body["options_chain"]) == 10
    # Honest engine status: forced fallback.
    assert body["engine_status"]["engine_in_use"] == "numeric_fallback"
    # Provenance present and labeled.
    assert len(body["wolfram_computations"]) > 0
    assert all(c["engine"] == "numeric_fallback" for c in body["wolfram_computations"])
    # The deterministic fake-groq summary flows through.
    assert body["risk_summary"]


@pytest.mark.usefixtures("fake_groq")
def test_analyze_with_positions_nonzero_greeks(test_client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "symbol": "SPY",
        "dte_max": 365,
        "positions": [
            {
                "symbol": "SPY",
                "instrument": "call",
                "strike": 530.0,
                "expiry": "2027-01-15",
                "quantity": 10,
            }
        ],
    }
    resp = test_client.post("/analyze", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["portfolio_greeks"]["delta"] != 0.0


def test_analyze_bad_symbol_422(test_client) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.post("/analyze", json={"symbol": "12 3$", "dte_max": 7})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert body["field_errors"]


def test_analyze_extra_field_rejected(test_client) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.post(
        "/analyze", json={"symbol": "SPY", "dte_max": 7, "surprise": True}
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"


def test_analyze_unknown_symbol_404(test_client) -> None:  # type: ignore[no-untyped-def]
    resp = test_client.post("/analyze", json={"symbol": "ZZZ", "dte_max": 7})
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"
