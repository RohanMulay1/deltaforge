/**
 * HTTP client for the DeltaForge backend (ARCHITECTURE.md §10.2).
 *
 * `analyze()` is the non-stream POST path used by tests/fallback. The streaming
 * path lives in `sse.ts`. Every payload is validated with Zod (`fail loud`).
 */

import {
  analyzeResponseSchema,
  engineStatusSchema,
  portfolioGreeksSchema,
  scenarioSurfaceSchema,
} from "@/lib/api/schemas";
import type {
  AnalyzeResponse,
  EngineStatus,
  PortfolioGreeks,
  PortfolioPosition,
  ScenarioSurface,
} from "@/types";

const DEFAULT_BASE_URL = "http://localhost:8000";

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_BASE_URL;
}

/** Error envelope shape (§7) — `detail` is what the UI surfaces. */
interface ErrorEnvelopeLike {
  detail?: string;
  error?: string;
}

async function readErrorDetail(res: Response): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as ErrorEnvelopeLike;
  return body.detail ?? body.error ?? `HTTP ${res.status}`;
}

export interface AnalyzeParams {
  symbol: string;
  dteMax: number;
  positions?: PortfolioPosition[];
  signal?: AbortSignal;
}

/** Non-stream POST /analyze → validated AnalyzeResponse. */
export async function analyze(params: AnalyzeParams): Promise<AnalyzeResponse> {
  const { symbol, dteMax, positions, signal } = params;
  const res = await fetch(`${getApiBaseUrl()}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbol,
      dte_max: dteMax,
      positions: positions ?? null,
    }),
    signal,
  });

  if (!res.ok) {
    throw new Error(await readErrorDetail(res));
  }

  return analyzeResponseSchema.parse(await res.json());
}

/** GET /health/wolfram → validated EngineStatus (backs SymbolicEngineBadge). */
export async function fetchWolframHealth(
  signal?: AbortSignal,
): Promise<EngineStatus> {
  const res = await fetch(`${getApiBaseUrl()}/health/wolfram`, { signal });

  if (!res.ok) {
    throw new Error(await readErrorDetail(res));
  }

  return engineStatusSchema.parse(await res.json());
}

export interface PortfolioGreeksParams {
  symbol: string;
  positions: PortfolioPosition[];
  dteMax?: number;
  signal?: AbortSignal;
}

/** POST /portfolio/greeks → validated PortfolioGreeks (rail aggregate). */
export async function fetchPortfolioGreeks(
  params: PortfolioGreeksParams,
): Promise<PortfolioGreeks> {
  const { symbol, positions, dteMax, signal } = params;
  const res = await fetch(`${getApiBaseUrl()}/portfolio/greeks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, positions, dte_max: dteMax }),
    signal,
  });

  if (!res.ok) {
    throw new Error(await readErrorDetail(res));
  }

  return portfolioGreeksSchema.parse(await res.json());
}

/** A (lo, hi, step) percent triple — matches the backend ScenarioRequest. */
export type RangeSpec = [number, number, number];

export interface ScenarioParams {
  positions: PortfolioPosition[];
  spotPctRange: RangeSpec;
  ivPctRange: RangeSpec;
  dteOverride?: number;
  portfolioId?: string;
  signal?: AbortSignal;
}

/** POST /scenario → validated ScenarioSurface (P&L grid for the panel). */
export async function fetchScenario(
  params: ScenarioParams,
): Promise<ScenarioSurface> {
  const { positions, spotPctRange, ivPctRange, dteOverride, portfolioId, signal } =
    params;
  const res = await fetch(`${getApiBaseUrl()}/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      positions: positions.length > 0 ? positions : null,
      portfolio_id: portfolioId ?? null,
      spot_pct_range: spotPctRange,
      iv_pct_range: ivPctRange,
      dte_override: dteOverride ?? null,
    }),
    signal,
  });

  if (!res.ok) {
    throw new Error(await readErrorDetail(res));
  }

  return scenarioSurfaceSchema.parse(await res.json());
}
