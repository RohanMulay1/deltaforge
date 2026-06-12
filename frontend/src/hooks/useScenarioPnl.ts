"use client";

/**
 * useScenarioPnl — debounced, React-Query-cached POST /scenario
 * (ARCHITECTURE.md §10.3, P2). The spot%/IV/DTE slider values are debounced
 * (~200ms) so dragging a slider collapses into a single kernel-backed grid
 * request; identical grids are served from cache.
 *
 * Returns the real `ScenarioSurface` (P&L grid + breakeven + WL expression for
 * the strip). A kernel failure degrades to the labeled numeric fallback inside
 * the service, so the surface still renders honestly.
 */

import { useEffect, useMemo, useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { fetchScenario, type RangeSpec } from "@/lib/api/client";
import type { PortfolioPosition, ScenarioSurface } from "@/types";

const DEBOUNCE_MS = 200;

export interface ScenarioControls {
  /** ± spot move span, in percent (e.g. 15 → −15%…+15%). */
  spotSpanPct: number;
  /** spot grid step, percent. */
  spotStepPct: number;
  /** ± IV move span, in percent points. */
  ivSpanPct: number;
  /** IV grid step, percent. */
  ivStepPct: number;
  /** DTE override (days), or null to use the underlying's near expiry. */
  dteOverride: number | null;
}

export interface UseScenarioPnlResult {
  surface: ScenarioSurface | undefined;
  isFetching: boolean;
  isError: boolean;
  error: string | null;
  enabled: boolean;
}

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function toRange(span: number, step: number): RangeSpec {
  const safeSpan = Math.max(0, span);
  const safeStep = step > 0 ? step : 1;
  return [-safeSpan, safeSpan, safeStep];
}

export function useScenarioPnl(
  positions: PortfolioPosition[],
  controls: ScenarioControls,
): UseScenarioPnlResult {
  const debounced = useDebounced(controls, DEBOUNCE_MS);

  const spotRange = useMemo(
    () => toRange(debounced.spotSpanPct, debounced.spotStepPct),
    [debounced.spotSpanPct, debounced.spotStepPct],
  );
  const ivRange = useMemo(
    () => toRange(debounced.ivSpanPct, debounced.ivStepPct),
    [debounced.ivSpanPct, debounced.ivStepPct],
  );

  const wirePositions = useMemo(
    () => positions.map((p) => ({ ...p, id: null })),
    [positions],
  );

  const enabled = positions.length > 0;

  const queryKey = useMemo(
    () => [
      "scenario",
      JSON.stringify(
        wirePositions.map((p) => [
          p.symbol,
          p.instrument,
          p.strike,
          p.expiry,
          p.quantity,
          p.avg_price,
        ]),
      ),
      spotRange,
      ivRange,
      debounced.dteOverride,
    ],
    [wirePositions, spotRange, ivRange, debounced.dteOverride],
  );

  const query = useQuery({
    queryKey,
    enabled,
    queryFn: ({ signal }) =>
      fetchScenario({
        positions: wirePositions,
        spotPctRange: spotRange,
        ivPctRange: ivRange,
        dteOverride: debounced.dteOverride ?? undefined,
        signal,
      }),
    staleTime: 30_000,
    retry: 1,
  });

  return {
    surface: enabled ? query.data : undefined,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error instanceof Error ? query.error.message : null,
    enabled,
  };
}
