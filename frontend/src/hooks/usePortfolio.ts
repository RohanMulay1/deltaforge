"use client";

/**
 * usePortfolio — client-side portfolio state (ARCHITECTURE.md §10.3). A zustand
 * store holds the rail's working positions BEFORE/independent of any server
 * round-trip. Adds, removes, and bulk CSV imports all mutate immutably (new
 * arrays, never in-place), satisfying the codebase immutability rule.
 *
 * Positions carry the canonical wire shape (`PortfolioPosition`, snake_case);
 * each gets a stable client id so the virtualized list + per-row explain keys
 * stay consistent across re-renders.
 */

import { create } from "zustand";

import type { PortfolioPosition } from "@/types";

/** A position guaranteed to carry a non-null client id for list keys. */
export type RailPosition = PortfolioPosition & { id: string };

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  const rand = Math.random().toString(36).slice(2, 8);
  return `pos_${Date.now().toString(36)}_${idCounter}_${rand}`;
}

function withId(position: PortfolioPosition): RailPosition {
  return { ...position, id: position.id ?? nextId() };
}

interface PortfolioState {
  positions: RailPosition[];
  add: (position: PortfolioPosition) => void;
  addMany: (positions: PortfolioPosition[]) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const usePortfolioStore = create<PortfolioState>((set) => ({
  positions: [],
  add: (position) =>
    set((state) => ({ positions: [...state.positions, withId(position)] })),
  addMany: (incoming) =>
    set((state) => ({
      positions: [...state.positions, ...incoming.map(withId)],
    })),
  remove: (id) =>
    set((state) => ({
      positions: state.positions.filter((p) => p.id !== id),
    })),
  clear: () => set({ positions: [] }),
}));

export interface UsePortfolioResult {
  positions: RailPosition[];
  add: (position: PortfolioPosition) => void;
  addMany: (positions: PortfolioPosition[]) => void;
  remove: (id: string) => void;
  clear: () => void;
  /** The symbol the rail prices against (first position's, if any). */
  primarySymbol: string | null;
}

export function usePortfolio(): UsePortfolioResult {
  const positions = usePortfolioStore((s) => s.positions);
  const add = usePortfolioStore((s) => s.add);
  const addMany = usePortfolioStore((s) => s.addMany);
  const remove = usePortfolioStore((s) => s.remove);
  const clear = usePortfolioStore((s) => s.clear);

  const primarySymbol = positions.length > 0 ? positions[0].symbol : null;

  return { positions, add, addMany, remove, clear, primarySymbol };
}
