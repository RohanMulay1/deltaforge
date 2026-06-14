"use client";

/**
 * Shares one `useAnalysisStream` instance across routes via context so the
 * dashboard (`/`) and the IV Surface page (`/iv-surface`) read the SAME live
 * analysis without re-streaming. Mounted in `providers.tsx` inside the React
 * Query provider (the hook depends on `useQueryClient`).
 */

import { createContext, useContext, type ReactNode } from "react";

import {
  useAnalysisStream,
  type UseAnalysisStreamResult,
} from "@/hooks/useAnalysisStream";

const AnalysisStreamContext = createContext<UseAnalysisStreamResult | null>(
  null,
);

export function AnalysisStreamProvider({ children }: { children: ReactNode }) {
  const stream = useAnalysisStream();
  return (
    <AnalysisStreamContext.Provider value={stream}>
      {children}
    </AnalysisStreamContext.Provider>
  );
}

export function useAnalysisStreamContext(): UseAnalysisStreamResult {
  const ctx = useContext(AnalysisStreamContext);
  if (ctx === null) {
    throw new Error(
      "useAnalysisStreamContext must be used within an AnalysisStreamProvider",
    );
  }
  return ctx;
}
