/**
 * Canonical analysis fixture (ARCHITECTURE.md §10.1).
 *
 * Typed as `AnalysisResult` (the full §4.10 payload), snake_case, with engine
 * provenance set to `numeric_fallback` so a fixture is never mistaken for a
 * real kernel run. Imported ONLY by `*.stories.tsx` / `*.test.tsx`; ESLint
 * bans importing this from `src/app/**` and `src/components/**`.
 */

import type {
  AnalysisResult,
  Greeks,
  OptionQuote,
  WolframComputation,
} from "@/types";

const NOW = "2026-06-11T14:30:00Z";

function fallbackComputation(
  label: string,
  expression: string,
  resultNumeric: number,
): WolframComputation {
  return {
    label,
    expression,
    engine: "numeric_fallback",
    inputs: {},
    result_raw: null,
    result_numeric: resultNumeric,
    evaluated: false,
    duration_ms: null,
    fallback_reason: "kernel_unavailable",
    error: null,
    evaluated_at: NOW,
  };
}

function greeks(delta: number): Greeks {
  return { delta, gamma: 0.018, theta: -1.45, vega: 2.31, rho: 0.04 };
}

function quote(
  strike: number,
  type: "call" | "put",
  iv: number,
  bid: number,
  ask: number,
  volume: number,
  oi: number,
  ofi: number,
  delta: number,
): OptionQuote {
  return {
    strike,
    type,
    expiry: "2026-06-18",
    bid,
    ask,
    last_price: (bid + ask) / 2,
    volume,
    open_interest: oi,
    iv,
    ofi,
    greeks: greeks(delta),
    delta,
    moneyness: 725.43 / strike,
    wolfram: fallbackComputation(
      `Greeks ${type} ${strike}`,
      `D[bs[${strike}], S]`,
      delta,
    ),
  };
}

const CHAIN: OptionQuote[] = [
  quote(700, "call", 0.242, 26.8, 27.1, 4820, 12400, 0.62, 0.82),
  quote(710, "call", 0.214, 17.6, 17.9, 11200, 28400, 0.28, 0.68),
  quote(720, "call", 0.189, 9.7, 9.95, 24100, 62800, -0.06, 0.48),
  quote(725, "call", 0.178, 6.6, 6.85, 31400, 89200, -0.22, 0.38),
  quote(730, "call", 0.17, 4.2, 4.4, 22100, 74100, -0.38, 0.28),
  quote(740, "call", 0.161, 1.3, 1.42, 8900, 32400, -0.67, 0.11),
  quote(700, "put", 0.238, 1.2, 1.32, 3100, 9800, 0.71, -0.18),
  quote(710, "put", 0.212, 2.7, 2.85, 8400, 22100, 0.34, -0.32),
  quote(720, "put", 0.188, 5.6, 5.8, 21800, 58900, -0.09, -0.52),
  quote(725, "put", 0.177, 7.8, 8.0, 28600, 82400, -0.28, -0.62),
  quote(730, "put", 0.169, 10.6, 10.85, 19200, 61200, -0.44, -0.72),
  quote(740, "put", 0.16, 17.7, 18.0, 6800, 24100, -0.72, -0.89),
];

const HEDGE_WOLFRAM = fallbackComputation(
  "Delta-Neutral Hedge (NMinimize)",
  "NMinimize[{(h * 0.482100 - 0.000000)^2, -100 <= h <= 100}, h]",
  2,
);

const SCENARIO_WOLFRAM = fallbackComputation(
  "P&L Surface",
  "pnl[S, sig, T] = portfolioValue[S, sig, T] - baseValue",
  0,
);

export const ANALYSIS_FIXTURE: AnalysisResult = {
  symbol: "SPY",
  spot_price: 725.43,
  expiry: "2026-06-18",
  calls_count: 57,
  puts_count: 69,
  order_flow_imbalance: -0.1045,
  pin_risk_score: 0.66,
  iv_rank: 28.4,
  market: {
    symbol: "SPY",
    spot_price: 725.43,
    timestamp: NOW,
    expiry_used: "2026-06-18",
    near_expiry_filter_used: "<=7d",
    dte: 7,
    order_flow_imbalance: -0.1045,
    pin_risk_score: 0.66,
    max_pain_strike: 725,
    iv_stats: {
      iv_rank: 28.4,
      iv_percentile: 31.2,
      atm_iv: 0.178,
      iv_30d_high: 0.31,
      iv_30d_low: 0.14,
      term_structure: [
        ["2026-06-18", 0.178],
        ["2026-07-18", 0.192],
      ],
    },
    calls_count: 57,
    puts_count: 69,
    chain: CHAIN,
    data_source: "yfinance",
  },
  options_chain: CHAIN,
  portfolio_greeks: {
    delta: -0.23,
    gamma: 0.018,
    theta: -1.45,
    vega: 2.31,
    rho: 0.04,
    net_delta_dollars: -16685.0,
    beta_weighted_delta: -0.21,
    per_position: {},
    wolfram: fallbackComputation(
      "Portfolio Aggregate Greeks",
      "Total[bsGreeks @@@ book]",
      -0.23,
    ),
  },
  hedge: {
    symbol: "SPY",
    delta_neutral_ratio: 0.4821,
    contracts_to_trade: 2,
    option_type_to_trade: "call",
    strike_to_trade: 725.0,
    expiry_to_trade: "2026-06-18",
    expected_pnl_range: [-245.5, 892.3],
    current_portfolio_delta: -0.23,
    residual_delta_after_hedge: 0.004,
    delta_target: 0.0,
    wolfram_computation_used:
      "NMinimize[{(h * 0.482100 - 0.000000)^2, -100 <= h <= 100}, h]",
    wolfram: HEDGE_WOLFRAM,
    reasoning:
      "Numeric-fallback delta-neutral hedge: portfolio delta of -0.23 offset by 2 call contracts at the 725 strike. Expected P&L range accounts for a 1-sigma IV move over the DTE window.",
  },
  scenario: {
    x_axis: { name: "spot_pct", values: [-5, -2.5, 0, 2.5, 5] },
    y_axis: { name: "iv_pct", values: [-10, 0, 10] },
    pnl_grid: [
      [-820, -410, 0, 415, 835],
      [-760, -380, 0, 390, 790],
      [-700, -350, 0, 360, 730],
    ],
    base_pnl: 0,
    breakeven_spot: 725.0,
    wolfram: SCENARIO_WOLFRAM,
    is_stub: true,
  },
  risk_summary:
    "SPY options chain shows moderate put-side pressure (OFI: -0.10) with elevated pin risk at the 725 strike (score: 0.66). The delta-neutral hedge recommends 2 calls at 725 to flatten portfolio delta from -0.23 to near-zero. IV rank at 28.4% suggests hedging is cost-effective at current implied volatility.",
  wolfram_computation_used:
    "NMinimize[{(h * 0.482100 - 0.000000)^2, -100 <= h <= 100}, h]",
  wolfram_computations: [
    HEDGE_WOLFRAM,
    SCENARIO_WOLFRAM,
    ...CHAIN.map((q) => q.wolfram).filter(
      (w): w is WolframComputation => w !== null,
    ),
  ],
  engine_status: {
    wolfram_available: false,
    engine_in_use: "numeric_fallback",
    kernel_version: null,
    pool_size: 0,
    healthy_sessions: 0,
    last_probe_ms: null,
    reason: "kernel_unavailable",
    note: "Fixture data — numeric fallback, not a real kernel run.",
    last_checked: NOW,
  },
  analysis_id: null,
  generated_at: NOW,
  disclaimer: "Informational only. Not investment advice. No live execution.",
};
