"use client";

/**
 * Shape-matched skeletons (ARCHITECTURE.md §10.1) — keep CLS < 0.1 by reserving
 * the same footprint as the resolved panel. Pure CSS shimmer, no layout
 * thrash (animates only `background-position`, compositor-friendly).
 */

import type { CSSProperties } from "react";

interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  radius?: number;
  className?: string;
  style?: CSSProperties;
}

const SHIMMER_STYLE: CSSProperties = {
  background:
    "linear-gradient(90deg, var(--df-surface) 25%, var(--df-border-strong) 37%, var(--df-surface) 63%)",
  backgroundSize: "400% 100%",
  animation: "df-shimmer 1.4s ease infinite",
};

export function Skeleton({
  width = "100%",
  height = 16,
  radius = 8,
  className,
  style,
}: SkeletonProps) {
  return (
    <div
      className={className}
      aria-hidden="true"
      style={{ ...SHIMMER_STYLE, width, height, borderRadius: radius, ...style }}
    />
  );
}

/** A skeleton sized for one HUD card. */
export function HudCardSkeleton() {
  return (
    <div className="cb-card cb-hud-card px-5 py-4">
      <Skeleton width={64} height={9} radius={4} style={{ marginBottom: 14 }} />
      <Skeleton width={96} height={24} radius={6} />
    </div>
  );
}

/** A skeleton sized for the options chain table body. */
export function ChainSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="cb-card overflow-hidden">
      <div
        className="px-5 py-3.5"
        style={{ borderBottom: "1px solid var(--df-border)" }}
      >
        <Skeleton width={120} height={12} radius={4} />
      </div>
      <div className="px-5 py-3 flex flex-col gap-3">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} height={18} radius={6} />
        ))}
      </div>
    </div>
  );
}

/** A generic card-shaped skeleton block (IV surface / hedge). */
export function CardSkeleton({ height = 220 }: { height?: number }) {
  return (
    <div className="cb-card overflow-hidden">
      <div
        className="px-5 py-3.5"
        style={{ borderBottom: "1px solid var(--df-border)" }}
      >
        <Skeleton width={160} height={12} radius={4} />
      </div>
      <div style={{ padding: 16 }}>
        <Skeleton height={height} radius={12} />
      </div>
    </div>
  );
}
