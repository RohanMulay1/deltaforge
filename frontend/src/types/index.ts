/**
 * Frontend contract types — Zod-inferred, snake_case (ARCHITECTURE.md §10.4).
 *
 * `src/lib/api/schemas.ts` is the single source of truth; this module only
 * re-exports `z.infer` types so every component imports from `@/types` and
 * never re-declares wire shapes. Field names are IDENTICAL to §4.
 */

import type { z } from "zod";

import type {
  analyzeRequestSchema,
  analyzeResponseSchema,
  engineStatusSchema,
  greeksSchema,
  hedgeRecommendationSchema,
  ivStatsSchema,
  marketSnapshotSchema,
  optionQuoteSchema,
  portfolioGreeksSchema,
  portfolioPositionSchema,
  portfolioSchema,
  scenarioAxisSchema,
  scenarioSurfaceSchema,
  stageEventSchema,
  summaryEventSchema,
  wolframComputationSchema,
} from "@/lib/api/schemas";

export type Greeks = z.infer<typeof greeksSchema>;
export type WolframComputation = z.infer<typeof wolframComputationSchema>;
export type EngineStatus = z.infer<typeof engineStatusSchema>;
export type OptionQuote = z.infer<typeof optionQuoteSchema>;
export type IVStats = z.infer<typeof ivStatsSchema>;
export type MarketSnapshot = z.infer<typeof marketSnapshotSchema>;
export type PortfolioPosition = z.infer<typeof portfolioPositionSchema>;
export type PortfolioGreeks = z.infer<typeof portfolioGreeksSchema>;
export type Portfolio = z.infer<typeof portfolioSchema>;
export type HedgeRecommendation = z.infer<typeof hedgeRecommendationSchema>;
export type ScenarioAxis = z.infer<typeof scenarioAxisSchema>;
export type ScenarioSurface = z.infer<typeof scenarioSurfaceSchema>;
export type AnalyzeResponse = z.infer<typeof analyzeResponseSchema>;
export type AnalyzeRequest = z.infer<typeof analyzeRequestSchema>;

/** The fully-assembled dashboard payload — alias of the canonical response. */
export type AnalysisResult = AnalyzeResponse;

export type StageEvent = z.infer<typeof stageEventSchema>;
export type SummaryEvent = z.infer<typeof summaryEventSchema>;

/** Pipeline stage names (§1 rule 5 / §10.4). */
export type StageName =
  | "market_data"
  | "greeks"
  | "iv_surface"
  | "portfolio"
  | "hedge"
  | "scenario"
  | "summary";

/** Per-panel 4-state machine (§10.1 / §10.4). */
export type StageStatus = "idle" | "loading" | "ready" | "error";

/** The engine discriminator union (§1 rule 2). */
export type WolframEngine = "wolfram" | "numeric_fallback";
