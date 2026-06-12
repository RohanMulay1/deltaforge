/**
 * Shared React Query client (ARCHITECTURE.md §10.2).
 *
 * The streamed analysis is written into the cache under
 * `['analysis', symbol, dteMax]` via `setQueryData`; health polling lives under
 * `['wolfram-health']`. A single factory keeps the config in one place.
 */

import { QueryClient } from "@tanstack/react-query";

import type { StageName } from "@/types";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // The stream is the source of freshness; avoid surprise refetches that
        // would clobber the assembled analysis. Health polling sets its own
        // refetchInterval explicitly.
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
}

export const analysisQueryKey = (symbol: string, dteMax: number) =>
  ["analysis", symbol, dteMax] as const;

export const wolframHealthQueryKey = () => ["wolfram-health"] as const;

/** Initial idle stage map for a fresh analysis (§10.2). */
export const STAGE_NAMES: readonly StageName[] = [
  "market_data",
  "greeks",
  "iv_surface",
  "portfolio",
  "hedge",
  "scenario",
  "summary",
];
