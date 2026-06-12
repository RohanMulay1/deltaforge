"use client";

/**
 * SymbolicEngineBadge — the honest live engine pill (ARCHITECTURE.md §10.3).
 *
 * Polls /health/wolfram via `useWolframHealth`. Copy is fixed:
 *   - engine === "wolfram"          → green  "WOLFRAM KERNEL · LIVE" (+latency)
 *   - engine === "numeric_fallback" → amber  "NUMERIC FALLBACK — NOT WOLFRAM"
 *   - checking / unknown            → gray   "CHECKING…"
 *
 * Replaces the static "WOLFRAM MCP / READY" lie in Header.tsx.
 */

import { useWolframHealth } from "@/hooks/useWolframHealth";

type BadgeTone = "live" | "fallback" | "checking";

interface BadgeView {
  tone: BadgeTone;
  color: string;
  label: string;
  detail?: string;
}

const TONE_COLOR: Record<BadgeTone, string> = {
  live: "var(--df-up, #05b169)",
  fallback: "var(--df-warn, #f4b000)",
  checking: "var(--df-text-muted, #7c828a)",
};

function StatusDot({ color, pulse }: { color: string; pulse: boolean }) {
  return (
    <span className="relative flex h-2 w-2">
      {pulse && (
        <span
          className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-50"
          style={{ background: color }}
        />
      )}
      <span
        className="relative inline-flex rounded-full h-2 w-2"
        style={{ background: color }}
      />
    </span>
  );
}

export function SymbolicEngineBadge() {
  const { status, isLoading, isError } = useWolframHealth();

  const view: BadgeView = (() => {
    if (isLoading || (!status && !isError)) {
      return { tone: "checking", color: TONE_COLOR.checking, label: "CHECKING…" };
    }
    if (status?.engine_in_use === "wolfram") {
      const latency =
        status.last_probe_ms != null
          ? `${Math.round(status.last_probe_ms)}ms`
          : undefined;
      return {
        tone: "live",
        color: TONE_COLOR.live,
        label: "WOLFRAM KERNEL · LIVE",
        detail: latency,
      };
    }
    // numeric_fallback OR health-check error → honest fallback labeling.
    return {
      tone: "fallback",
      color: TONE_COLOR.fallback,
      label: "NUMERIC FALLBACK — NOT WOLFRAM",
      detail: status?.reason ?? undefined,
    };
  })();

  return (
    <div
      className="flex items-center gap-2"
      title={status?.note ?? undefined}
      aria-live="polite"
    >
      <StatusDot color={view.color} pulse={view.tone !== "checking"} />
      <span
        className="text-[11px] font-semibold tracking-wide"
        style={{ color: view.color }}
      >
        {view.label}
      </span>
      {view.detail && (
        <span className="text-[11px] font-mono" style={{ color: "#a8acb3" }}>
          {view.detail}
        </span>
      )}
    </div>
  );
}
