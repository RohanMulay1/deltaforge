"use client";

/**
 * usePortfolioGreeks — debounced POST /portfolio/greeks for the rail aggregate
 * (ARCHITECTURE.md §3, §10.3). Distinct from the full /analyze pipeline: the
 * rail needs a cheap, frequently-refreshed aggregate Greeks read as the user
 * edits positions.
 *
 * The positions array is debounced (~350ms) so rapid add/remove bursts collapse
 * into one kernel-backed request. Each successful response is the real,
 * kernel-verified `PortfolioGreeks` (carrying its own `wolfram` provenance) —
 * the HedgePanel and HUD consume `portfolio_greeks.delta` from here.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { fetchPortfolioGreeks } from "@/lib/api/client";
import type { PortfolioGreeks, PortfolioPosition } from "@/types";

const DEBOUNCE_MS = 350;

export interface UsePortfolioGreeksResult {
  greeks: PortfolioGreeks | undefined;
  isFetching: boolean;
  isError: boolean;
  error: string | null;
}

/**
 * Debounce an arbitrary value. Returns the latest value only after `delay` ms
 * of no further changes.
 */
function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

/** Stable hash of the positions so the query key only changes on real edits. */
function positionsKey(symbol: string | null, positions: PortfolioPosition[]): string {
  return JSON.stringify({
    symbol,
    p: positions.map((p) => [
      p.symbol,
      p.instrument,
      p.strike,
      p.expiry,
      p.quantity,
      p.avg_price,
    ]),
  });
}

export function usePortfolioGreeks(
  positions: PortfolioPosition[],
  symbol: string | null,
  dteMax = 7,
): UsePortfolioGreeksResult {
  const debouncedPositions = useDebounced(positions, DEBOUNCE_MS);
  const debouncedKey = useMemo(
    () => positionsKey(symbol, debouncedPositions),
    [symbol, debouncedPositions],
  );

  // Strip transient client ids before sending (backend assigns its own).
  const wirePositions = useRef<PortfolioPosition[]>([]);
  wirePositions.current = debouncedPositions.map((p) => ({ ...p, id: null }));

  const enabled = symbol !== null && debouncedPositions.length > 0;

  const query = useQuery({
    queryKey: ["portfolio-greeks", debouncedKey],
    enabled,
    queryFn: ({ signal }) =>
      fetchPortfolioGreeks({
        symbol: symbol as string,
        positions: wirePositions.current,
        dteMax,
        signal,
      }),
    staleTime: 15_000,
    retry: 1,
  });

  return {
    greeks: enabled ? query.data : undefined,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
