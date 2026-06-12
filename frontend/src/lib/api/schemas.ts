/**
 * Single source of truth for the DeltaForge wire contract (ARCHITECTURE.md §4 + §10.4).
 *
 * All keys are snake_case — IDENTICAL to the backend Pydantic models. There is
 * NO camelCase transform layer (§1 rule 1). TS contract types are produced by
 * `z.infer` over these schemas and re-exported from `@/types`.
 *
 * The engine discriminator union is `"wolfram" | "numeric_fallback"` (§1 rule 2).
 * `wolfram` means a real LOCAL Wolfram Engine kernel ran the computation;
 * `numeric_fallback` is the labeled scipy/numpy path — never styled as Wolfram.
 */

import { z } from "zod";

// ─── Enums / unions ─────────────────────────────────────────────────────────

export const optionTypeSchema = z.enum(["call", "put"]);

export const instrumentTypeSchema = z.enum(["equity", "call", "put"]);

/** The ONE canonical engine discriminator (§1 rule 2). */
export const wolframEngineSchema = z.enum(["wolfram", "numeric_fallback"]);

export const pipelineStageSchema = z.enum([
  "market_data",
  "greeks",
  "iv_surface",
  "portfolio",
  "hedge",
  "scenario",
  "summary",
]);

// ─── Greeks (§4.2) ──────────────────────────────────────────────────────────

export const greeksSchema = z.object({
  delta: z.number(),
  gamma: z.number(),
  theta: z.number(),
  vega: z.number(),
  rho: z.number().default(0),
});

// ─── Wolfram provenance (§4.3) ──────────────────────────────────────────────

export const wolframComputationSchema = z.object({
  label: z.string(),
  expression: z.string(),
  engine: wolframEngineSchema,
  inputs: z.record(z.string(), z.union([z.number(), z.string()])).default({}),
  result_raw: z.string().nullable().default(null),
  result_numeric: z.number().nullable().default(null),
  evaluated: z.boolean(),
  duration_ms: z.number().nullable().default(null),
  fallback_reason: z.string().nullable().default(null),
  error: z.string().nullable().default(null),
  evaluated_at: z.string(),
});

// ─── Engine status (§4.9) ───────────────────────────────────────────────────

export const engineStatusSchema = z.object({
  wolfram_available: z.boolean(),
  engine_in_use: wolframEngineSchema,
  kernel_version: z.string().nullable().default(null),
  pool_size: z.number().default(0),
  healthy_sessions: z.number().default(0),
  last_probe_ms: z.number().nullable().default(null),
  reason: z.string().nullable().default(null),
  note: z.string(),
  last_checked: z.string(),
});

// ─── Market (§4.5) ──────────────────────────────────────────────────────────

export const optionQuoteSchema = z.object({
  strike: z.number(),
  type: optionTypeSchema,
  expiry: z.string(),
  bid: z.number(),
  ask: z.number(),
  last_price: z.number(),
  volume: z.number(),
  open_interest: z.number(),
  iv: z.number(),
  ofi: z.number(),
  greeks: greeksSchema,
  delta: z.number(),
  moneyness: z.number(),
  wolfram: wolframComputationSchema.nullable().default(null),
});

export const ivStatsSchema = z.object({
  iv_rank: z.number(),
  iv_percentile: z.number(),
  atm_iv: z.number(),
  iv_30d_high: z.number(),
  iv_30d_low: z.number(),
  term_structure: z.array(z.tuple([z.string(), z.number()])).default([]),
});

export const marketSnapshotSchema = z.object({
  symbol: z.string(),
  spot_price: z.number(),
  timestamp: z.string(),
  expiry_used: z.string(),
  near_expiry_filter_used: z.string(),
  dte: z.number(),
  order_flow_imbalance: z.number(),
  pin_risk_score: z.number(),
  max_pain_strike: z.number(),
  iv_stats: ivStatsSchema,
  calls_count: z.number(),
  puts_count: z.number(),
  chain: z.array(optionQuoteSchema),
  data_source: z.string().default("yfinance"),
});

// ─── Portfolio (§4.6) ───────────────────────────────────────────────────────

export const portfolioPositionSchema = z.object({
  id: z.string().nullable().default(null),
  symbol: z.string(),
  instrument: instrumentTypeSchema.default("call"),
  strike: z.number().nullable().default(null),
  expiry: z.string().nullable().default(null),
  quantity: z.number().int(),
  avg_price: z.number().nullable().default(null),
  greeks: greeksSchema.nullable().default(null),
  wolfram: wolframComputationSchema.nullable().default(null),
});

export const portfolioGreeksSchema = z.object({
  delta: z.number(),
  gamma: z.number(),
  theta: z.number(),
  vega: z.number(),
  rho: z.number().default(0),
  net_delta_dollars: z.number(),
  beta_weighted_delta: z.number().nullable().default(null),
  per_position: z.record(z.string(), greeksSchema).default({}),
  wolfram: wolframComputationSchema.nullable().default(null),
});

export const portfolioSchema = z.object({
  id: z.string(),
  name: z.string(),
  positions: z.array(portfolioPositionSchema),
  created_at: z.string(),
  updated_at: z.string(),
});

// ─── Hedge (§4.7) ───────────────────────────────────────────────────────────

export const hedgeRecommendationSchema = z.object({
  symbol: z.string(),
  delta_neutral_ratio: z.number(),
  contracts_to_trade: z.number().int(),
  option_type_to_trade: optionTypeSchema,
  strike_to_trade: z.number(),
  expiry_to_trade: z.string(),
  expected_pnl_range: z.tuple([z.number(), z.number()]),
  current_portfolio_delta: z.number(),
  residual_delta_after_hedge: z.number(),
  delta_target: z.number(),
  wolfram_computation_used: z.string(),
  wolfram: wolframComputationSchema,
  reasoning: z.string(),
});

// ─── Scenario (§4.8) ────────────────────────────────────────────────────────

export const scenarioAxisSchema = z.object({
  name: z.enum(["spot_pct", "iv_pct", "dte"]),
  values: z.array(z.number()),
});

export const scenarioSurfaceSchema = z.object({
  x_axis: scenarioAxisSchema,
  y_axis: scenarioAxisSchema,
  pnl_grid: z.array(z.array(z.number())),
  base_pnl: z.number(),
  breakeven_spot: z.number().nullable().default(null),
  wolfram: wolframComputationSchema,
  is_stub: z.boolean().default(true),
});

// ─── Top-level /analyze response (§4.10) — the whole dashboard ───────────────

export const analyzeResponseSchema = z.object({
  symbol: z.string(),
  spot_price: z.number(),
  expiry: z.string(),
  calls_count: z.number(),
  puts_count: z.number(),
  order_flow_imbalance: z.number(),
  pin_risk_score: z.number(),
  iv_rank: z.number(),
  market: marketSnapshotSchema,
  options_chain: z.array(optionQuoteSchema),
  portfolio_greeks: portfolioGreeksSchema,
  hedge: hedgeRecommendationSchema,
  scenario: scenarioSurfaceSchema,
  risk_summary: z.string(),
  wolfram_computation_used: z.string(),
  wolfram_computations: z.array(wolframComputationSchema),
  engine_status: engineStatusSchema,
  analysis_id: z.string().nullable().default(null),
  generated_at: z.string(),
  disclaimer: z
    .string()
    .default("Informational only. Not investment advice. No live execution."),
});

// ─── Requests (§4.11) ───────────────────────────────────────────────────────

export const analyzeRequestSchema = z.object({
  symbol: z.string().min(1).max(8),
  dte_max: z.number().int().min(1).max(365).default(7),
  positions: z.array(portfolioPositionSchema).nullable().default(null),
});

// ─── SSE event payloads (§6) ────────────────────────────────────────────────

export const stageStatusEnumSchema = z.enum(["start", "done", "error"]);

export const stageEventSchema = z.object({
  stage: pipelineStageSchema,
  status: stageStatusEnumSchema,
});

export const summaryEventSchema = z.object({
  risk_summary: z.string(),
  summary_delta: z.string().optional(),
});
