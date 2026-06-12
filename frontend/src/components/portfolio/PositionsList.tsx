"use client";

/**
 * PositionsList — virtualized list of portfolio legs (ARCHITECTURE.md §10.3).
 * Uses `@tanstack/react-virtual` so a large pasted book stays smooth in the
 * fixed-height rail. Empty state is explicit (no fake rows).
 */

import { useRef } from "react";

import { useVirtualizer } from "@tanstack/react-virtual";

import { PositionRow } from "@/components/portfolio/PositionRow";
import type { RailPosition } from "@/hooks/usePortfolio";

interface PositionsListProps {
  positions: RailPosition[];
  onRemove: (id: string) => void;
}

const ROW_HEIGHT = 50;
const MAX_VIEWPORT = 280;
const MUTED = "var(--df-text-muted, #7c828a)";

export function PositionsList({ positions, onRemove }: PositionsListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: positions.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 6,
  });

  if (positions.length === 0) {
    return (
      <div
        className="rounded-xl px-3 py-6 text-center font-mono text-[10px]"
        style={{ border: "1px dashed var(--df-border-strong)", color: MUTED }}
      >
        No positions yet — add one or paste a CSV below.
      </div>
    );
  }

  const viewportHeight = Math.min(positions.length * ROW_HEIGHT, MAX_VIEWPORT);
  const items = virtualizer.getVirtualItems();

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: MUTED, letterSpacing: "0.12em" }}>
          Positions
        </span>
        <span className="font-mono text-[9px]" style={{ color: MUTED }}>
          {positions.length}
        </span>
      </div>

      <div ref={scrollRef} style={{ height: viewportHeight, overflowY: "auto" }}>
        <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
          {items.map((vItem) => {
            const position = positions[vItem.index];
            return (
              <div
                key={position.id}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  paddingBottom: 6,
                  transform: `translateY(${vItem.start}px)`,
                }}
              >
                <PositionRow position={position} onRemove={onRemove} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
