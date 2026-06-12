"""Phase 1 verification script — run this to confirm Agent 1 is working.

Usage:
    cd deltaforge/backend
    python test_agent1.py

Expected output: validated OptionsChainPayload JSON for SPY and QQQ.
"""

import json
import logging
import sys

from agents.market_data_agent import fetch_options_chain

# Configure structured JSON logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    stream=sys.stderr,
)

SYMBOLS = ["SPY", "QQQ"]
DTE_MAX = 14  # widen slightly for weekend/holiday tolerance


def main() -> None:
    results = {}
    for symbol in SYMBOLS:
        print(f"\n{'='*60}", flush=True)
        print(f"Fetching: {symbol}", flush=True)
        try:
            payload = fetch_options_chain(symbol, dte_max=DTE_MAX)
            data = payload.model_dump(mode="json")
            results[symbol] = data

            # Summary stats
            print(f"  Spot price    : ${payload.spot_price:.2f}")
            print(f"  Expiry used   : {payload.expiry_used}")
            print(f"  Calls filtered: {len(payload.calls)}")
            print(f"  Puts filtered : {len(payload.puts)}")
            print(f"  OFI           : {payload.order_flow_imbalance:+.4f}  (+ = call-heavy)")
            print(f"  Pin Risk Score: {payload.pin_risk_score:.4f}  (1.0 = max pin risk)")

        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            results[symbol] = {"error": str(exc)}

    print(f"\n{'='*60}")
    print("Full JSON payloads:\n")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
