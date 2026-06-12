"use client";

/**
 * useChainRows — memoized selector that flattens an OptionQuote chain into the
 * row model the virtualized table renders (ARCHITECTURE.md §10.3).
 *
 * Rows are calls-then-puts, each group sorted by strike ascending. The ATM
 * anchor (row nearest spot) is surfaced so the table can scroll to it and draw
 * the sticky ATM divider. `maxVolume` powers the per-row volume bar.
 */

import { useMemo } from "react";

import type { OptionQuote } from "@/types";

/** Distance from spot at which a strike is considered ATM (terminal divider). */
const ATM_TOLERANCE = 2.5;

export interface ChainRow {
  key: string;
  strike: number;
  type: "call" | "put";
  iv: number;
  bid: number;
  ask: number;
  volume: number;
  openInterest: number;
  ofi: number;
  delta: number;
  isAtm: boolean;
  /** The source quote (carries `wolfram` provenance for the Explainable cell). */
  quote: OptionQuote;
}

export interface ChainRowsResult {
  rows: ChainRow[];
  /** Index of the row nearest spot, for ATM-anchored scroll. -1 when empty. */
  atmIndex: number;
  maxVolume: number;
}

function sortByStrike(a: OptionQuote, b: OptionQuote): number {
  return a.strike - b.strike;
}

export function useChainRows(
  chain: readonly OptionQuote[],
  spotPrice: number,
): ChainRowsResult {
  return useMemo(() => {
    const calls = chain.filter((q) => q.type === "call").sort(sortByStrike);
    const puts = chain.filter((q) => q.type === "put").sort(sortByStrike);
    const ordered = [...calls, ...puts];

    let maxVolume = 1;
    let atmIndex = -1;
    let atmDistance = Number.POSITIVE_INFINITY;

    const rows: ChainRow[] = ordered.map((quote, index) => {
      maxVolume = Math.max(maxVolume, quote.volume);
      const distance = Math.abs(quote.strike - spotPrice);
      if (distance < atmDistance) {
        atmDistance = distance;
        atmIndex = index;
      }
      return {
        key: `${quote.type}-${quote.strike}-${quote.expiry}-${index}`,
        strike: quote.strike,
        type: quote.type,
        iv: quote.iv,
        bid: quote.bid,
        ask: quote.ask,
        volume: quote.volume,
        openInterest: quote.open_interest,
        ofi: quote.ofi,
        delta: quote.delta,
        isAtm: distance < ATM_TOLERANCE,
        quote,
      };
    });

    return { rows, atmIndex, maxVolume };
  }, [chain, spotPrice]);
}
