"use client";

/**
 * ExplainContext — the single source of "what is the drawer showing?" state
 * (ARCHITECTURE.md §10.3, the differentiator). A tiny zustand store holds the
 * currently-open `WolframComputation` (plus an optional human title). Any
 * `<Explainable>` opens the ONE shared `<ExplainDrawer>` by setting it.
 *
 * Using a store (not React context) keeps every `<Explainable>` cheap: opening
 * the drawer never re-renders the whole tree, only the drawer + the active
 * trigger. `ExplainProvider` is a no-op wrapper kept for symmetry with the
 * page mount contract and to allow future SSR-safe hydration if needed.
 */

import type { ReactNode } from "react";

import { create } from "zustand";

import type { WolframComputation } from "@/types";

export interface ExplainTarget {
  /** Optional override title; falls back to `computation.label`. */
  title?: string;
  computation: WolframComputation;
}

interface ExplainState {
  active: ExplainTarget | null;
  open: (target: ExplainTarget) => void;
  close: () => void;
}

export const useExplainStore = create<ExplainState>((set) => ({
  active: null,
  open: (target) => set({ active: target }),
  close: () => set({ active: null }),
}));

/** Open the shared drawer for a computation. */
export function useOpenExplain(): (target: ExplainTarget) => void {
  return useExplainStore((s) => s.open);
}

/** Read the currently-active drawer target + a close handle. */
export function useExplainTarget(): {
  active: ExplainTarget | null;
  close: () => void;
} {
  const active = useExplainStore((s) => s.active);
  const close = useExplainStore((s) => s.close);
  return { active, close };
}

/**
 * Provider boundary. The store is module-global (one drawer per app), so this
 * is intentionally a pass-through — it exists so `page.tsx` can wrap the tree
 * in `<ExplainProvider>` per the WS6 contract and so the mount point is
 * explicit and greppable.
 */
export function ExplainProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
