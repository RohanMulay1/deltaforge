"use client";

/**
 * Explainable — wraps any kernel-derived value so the user can audit it
 * (ARCHITECTURE.md §10.3, the anti-hallucination contract). Renders the child
 * value with a dotted underline + a small `ƒ` glyph; clicking opens the ONE
 * shared `<ExplainDrawer>` with the exact `WolframComputation` provenance.
 *
 * If no computation is attached (e.g. a not-yet-evaluated cell) it renders the
 * value plainly — no affordance, no lie. The glyph tints GREEN when a real
 * kernel ran it (`engine === "wolfram"`) and AMBER for the labeled numeric
 * fallback, so trust is visible even before the drawer opens.
 */

import type { ReactNode } from "react";

import { useOpenExplain } from "@/components/explain/ExplainContext";
import type { WolframComputation } from "@/types";

interface ExplainableProps {
  computation?: WolframComputation | null;
  /** Optional drawer title override; defaults to `computation.label`. */
  title?: string;
  children: ReactNode;
  className?: string;
}

const GREEN = "var(--df-up, #05b169)";
const AMBER = "var(--df-warn, #f4b000)";

export function Explainable({
  computation,
  title,
  children,
  className,
}: ExplainableProps) {
  const open = useOpenExplain();

  if (!computation) {
    return <span className={className}>{children}</span>;
  }

  const isWolfram = computation.engine === "wolfram";
  const glyphColor = isWolfram ? GREEN : AMBER;
  const label = title ?? computation.label;

  return (
    <button
      type="button"
      onClick={() => open({ title, computation })}
      className={className}
      title={`Explain: ${label}`}
      aria-label={`Show the Wolfram computation for ${label}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        background: "transparent",
        border: "none",
        padding: 0,
        margin: 0,
        cursor: "pointer",
        font: "inherit",
        color: "inherit",
        textDecoration: "underline dotted",
        textDecorationColor: "var(--df-text-dim)",
        textUnderlineOffset: "3px",
      }}
    >
      {children}
      <span
        aria-hidden="true"
        style={{
          fontFamily: "var(--font-mono, monospace)",
          fontStyle: "italic",
          fontSize: "0.72em",
          fontWeight: 700,
          lineHeight: 1,
          color: glyphColor,
          opacity: 0.9,
        }}
      >
        ƒ
      </span>
    </button>
  );
}
