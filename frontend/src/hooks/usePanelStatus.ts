"use client";

/**
 * usePanelStatus — derives the per-panel 4-state (idle|loading|ready|error)
 * from a stage map (ARCHITECTURE.md §10.1 / §10.2). Replaces the `previewMode`
 * boolean with an honest per-panel state machine.
 */

import type { StageMap } from "@/hooks/useAnalysisStream";
import type { StageName, StageStatus } from "@/types";

/**
 * Returns the 4-state for a given stage. When a higher-level error exists, any
 * not-yet-ready stage is reported as `error` so its panel shows the failure.
 */
export function usePanelStatus(
  stages: StageMap,
  stage: StageName,
  hasError = false,
): StageStatus {
  const status = stages[stage];
  if (hasError && status !== "ready") {
    return "error";
  }
  return status;
}

/** Pure variant for selecting a status outside React (tests/selectors). */
export function derivePanelStatus(
  stages: StageMap,
  stage: StageName,
  hasError = false,
): StageStatus {
  const status = stages[stage];
  if (hasError && status !== "ready") {
    return "error";
  }
  return status;
}
