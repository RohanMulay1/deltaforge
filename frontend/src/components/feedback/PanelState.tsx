"use client";

/**
 * PanelState — the per-panel 4-state switch (idle|loading|ready|error) that
 * replaces the global `previewMode` boolean (ARCHITECTURE.md §10.1).
 *
 * - idle    → empty placeholder (caller-supplied or default EmptyState)
 * - loading → shape-matched skeleton (caller-supplied)
 * - error   → inline error card with the failure detail
 * - ready   → the real children
 */

import type { ReactNode } from "react";

import { EmptyState } from "@/components/feedback/EmptyState";
import type { StageStatus } from "@/types";

interface PanelStateProps {
  status: StageStatus;
  children: ReactNode;
  skeleton: ReactNode;
  /** Rendered when status === "idle". Defaults to a neutral EmptyState. */
  idle?: ReactNode;
  /** Title for the default idle/empty placeholder. */
  emptyTitle?: string;
  emptyHint?: string;
  /** Error detail to surface when status === "error". */
  errorMessage?: string | null;
}

function ErrorCard({ message }: { message: string }) {
  return (
    <div
      className="flex items-center gap-2.5 rounded-2xl px-4 py-3 font-mono text-xs"
      role="alert"
      style={{
        background: "rgba(207,32,47,0.07)",
        border: "1px solid rgba(207,32,47,0.20)",
        color: "var(--df-down, #cf202f)",
        minHeight: 64,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: "var(--df-down, #cf202f)" }}
      />
      {message}
    </div>
  );
}

export function PanelState({
  status,
  children,
  skeleton,
  idle,
  emptyTitle = "Awaiting data",
  emptyHint = "Run an analysis to populate this panel",
  errorMessage,
}: PanelStateProps) {
  if (status === "loading") {
    return <>{skeleton}</>;
  }
  if (status === "error") {
    return <ErrorCard message={errorMessage ?? "Failed to load this panel"} />;
  }
  if (status === "idle") {
    return <>{idle ?? <EmptyState title={emptyTitle} hint={emptyHint} />}</>;
  }
  return <>{children}</>;
}
