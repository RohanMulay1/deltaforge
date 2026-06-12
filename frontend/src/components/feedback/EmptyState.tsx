"use client";

/**
 * EmptyState — the honest "no data yet" / "no exposure" panel (ARCHITECTURE.md
 * §10.1). Used as the `idle` rendering inside `<PanelState>`.
 */

import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  hint?: string;
  icon?: ReactNode;
  minHeight?: number;
}

export function EmptyState({
  title,
  hint,
  icon,
  minHeight = 160,
}: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 rounded-2xl text-center px-6"
      style={{
        minHeight,
        border: "1px dashed var(--df-border, var(--df-border-strong))",
        color: "var(--df-text-muted, #7c828a)",
      }}
    >
      {icon}
      <span className="font-mono text-xs font-semibold uppercase tracking-widest">
        {title}
      </span>
      {hint && (
        <span className="font-mono text-[11px]" style={{ opacity: 0.8 }}>
          {hint}
        </span>
      )}
    </div>
  );
}
