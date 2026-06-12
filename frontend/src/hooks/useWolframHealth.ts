"use client";

/**
 * useWolframHealth — polls GET /health/wolfram every 30s (ARCHITECTURE.md
 * §10.3). Backs `SymbolicEngineBadge`: green when the kernel canary round-trips
 * (`engine_in_use === "wolfram"`), amber on labeled `numeric_fallback`, gray
 * while checking.
 */

import { useQuery } from "@tanstack/react-query";

import { fetchWolframHealth } from "@/lib/api/client";
import { wolframHealthQueryKey } from "@/lib/query/queryClient";
import type { EngineStatus } from "@/types";

const HEALTH_POLL_INTERVAL_MS = 30_000;

export interface UseWolframHealthResult {
  status: EngineStatus | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function useWolframHealth(): UseWolframHealthResult {
  const query = useQuery({
    queryKey: wolframHealthQueryKey(),
    queryFn: ({ signal }) => fetchWolframHealth(signal),
    refetchInterval: HEALTH_POLL_INTERVAL_MS,
    staleTime: HEALTH_POLL_INTERVAL_MS,
    retry: 1,
  });

  return {
    status: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
