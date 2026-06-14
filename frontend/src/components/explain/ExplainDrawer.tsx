"use client";

/**
 * ExplainDrawer — the ONE shared provenance overlay (ARCHITECTURE.md §10.3,
 * THE differentiator). Driven by `ExplainContext`; renders for the active
 * `WolframComputation`:
 *
 *   inputs  →  exact WL expression (copyable)  →  kernel result_raw  →  numeric
 *
 * with a GREEN "verified by kernel" badge when `engine === "wolfram"` and an
 * AMBER "numeric fallback — NOT Wolfram" badge when `engine === "numeric_fallback"`.
 *
 * The expression + raw result are copy-to-clipboard so a customer can paste
 * them into Wolfram and reproduce the number — that round-trip IS the proof.
 */

import { useEffect, useState } from "react";

import { useExplainTarget } from "@/components/explain/ExplainContext";
import type { WolframComputation } from "@/types";

const GREEN = "var(--df-up, #05b169)";
const AMBER = "var(--df-warn, #f4b000)";
const PANEL_BG = "rgba(13,15,19,0.96)";

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1400);
    return () => clearTimeout(t);
  }, [copied]);

  const onCopy = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(value).then(() => setCopied(true));
    }
  };

  return (
    <button
      type="button"
      onClick={onCopy}
      className="font-mono text-[9px] font-bold uppercase tracking-widest px-2 py-1 rounded-md transition-colors"
      style={{
        background: copied ? "rgba(5,177,105,0.15)" : "var(--df-border)",
        color: copied ? GREEN : "var(--df-text-dim, #a8acb3)",
        border: "1px solid var(--df-border-strong)",
      }}
    >
      {copied ? "COPIED" : label}
    </button>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="font-mono text-[9px] font-bold uppercase tracking-widest mb-2"
      style={{ color: "var(--df-text-muted, #7c828a)", letterSpacing: "0.12em" }}
    >
      {children}
    </div>
  );
}

function VerificationBadge({ computation }: { computation: WolframComputation }) {
  const isWolfram = computation.engine === "wolfram";
  const color = isWolfram ? GREEN : AMBER;
  const label = isWolfram
    ? "VERIFIED BY KERNEL"
    : "NUMERIC FALLBACK — NOT WOLFRAM";
  return (
    <div className="flex flex-col gap-1">
      <span
        className="inline-flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 rounded-full self-start"
        style={{
          background: isWolfram ? "rgba(5,177,105,0.12)" : "rgba(244,176,0,0.12)",
          color,
          border: `1px solid ${isWolfram ? "rgba(5,177,105,0.30)" : "rgba(244,176,0,0.32)"}`,
          letterSpacing: "0.08em",
        }}
      >
        <span
          className="inline-block rounded-full"
          style={{ width: 6, height: 6, background: color }}
        />
        {label}
      </span>
      {!isWolfram && computation.fallback_reason && (
        <span className="font-mono text-[10px]" style={{ color: AMBER }}>
          reason: {computation.fallback_reason}
        </span>
      )}
    </div>
  );
}

function InputsTable({ inputs }: { inputs: WolframComputation["inputs"] }) {
  const entries = Object.entries(inputs ?? {});
  if (entries.length === 0) {
    return (
      <div className="font-mono text-[11px]" style={{ color: "var(--df-text-muted, #7c828a)" }}>
        no scalar inputs recorded
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="flex items-center justify-between rounded-lg px-3 py-2"
          style={{ background: "var(--df-surface)", border: "1px solid var(--df-border)" }}
        >
          <span className="font-mono text-[11px]" style={{ color: "var(--df-accent, #f5a623)" }}>
            {key}
          </span>
          <span className="font-mono text-[11px] tabular-nums" style={{ color: "var(--df-text, #fff)" }}>
            {typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : value}
          </span>
        </div>
      ))}
    </div>
  );
}

function CodeBlock({ value }: { value: string }) {
  return (
    <pre
      className="font-mono text-[11px] leading-relaxed rounded-xl px-3.5 py-3 overflow-x-auto whitespace-pre-wrap break-words"
      style={{
        background: "rgba(245,166,35,0.05)",
        border: "1px solid rgba(245,166,35,0.15)",
        color: "var(--df-text-dim, #a8acb3)",
        margin: 0,
      }}
    >
      {value}
    </pre>
  );
}

export function ExplainDrawer() {
  const { active, close } = useExplainTarget();

  // Close on Escape while open.
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, close]);

  if (!active) return null;

  const c = active.computation;
  const title = active.title ?? c.label;
  const numeric =
    c.result_numeric != null
      ? c.result_numeric.toLocaleString(undefined, { maximumFractionDigits: 8 })
      : "—";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Wolfram computation: ${title}`}
      style={{ position: "fixed", inset: 0, zIndex: 60 }}
    >
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close explanation"
        onClick={close}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.55)",
          backdropFilter: "blur(2px)",
          border: "none",
          cursor: "pointer",
        }}
      />

      {/* Right-side drawer */}
      <aside
        className="flex flex-col"
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          bottom: 0,
          width: "min(440px, 92vw)",
          background: PANEL_BG,
          borderLeft: "1px solid var(--df-border-strong, var(--df-border-strong))",
          backdropFilter: "blur(20px)",
          boxShadow: "-24px 0 60px rgba(0,0,0,0.45)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-start justify-between px-5 py-4"
          style={{ borderBottom: "1px solid var(--df-border)" }}
        >
          <div className="flex flex-col gap-1 min-w-0">
            <span
              className="font-mono text-[9px] font-bold uppercase tracking-widest"
              style={{ color: "var(--df-accent, #f5a623)", letterSpacing: "0.14em" }}
            >
              Wolfram Provenance
            </span>
            <span
              className="text-sm font-semibold truncate"
              style={{ letterSpacing: "-0.01em", color: "var(--df-text)" }}
            >
              {title}
            </span>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close"
            className="shrink-0 ml-3 w-7 h-7 flex items-center justify-center rounded-lg"
            style={{ background: "var(--df-border)", border: "1px solid var(--df-border-strong)", color: "var(--df-text)" }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
          <VerificationBadge computation={c} />

          <div>
            <SectionLabel>Inputs</SectionLabel>
            <InputsTable inputs={c.inputs} />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel>Wolfram Language Expression</SectionLabel>
              <CopyButton value={c.expression} label="Copy WL" />
            </div>
            <CodeBlock value={c.expression} />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <SectionLabel>Kernel Result (raw)</SectionLabel>
              {c.result_raw && <CopyButton value={c.result_raw} label="Copy" />}
            </div>
            {c.result_raw ? (
              <CodeBlock value={c.result_raw} />
            ) : (
              <div className="font-mono text-[11px]" style={{ color: "var(--df-text-muted, #7c828a)" }}>
                no kernel output (numeric fallback emits no WL result)
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl px-3.5 py-3" style={{ background: "var(--df-surface)", border: "1px solid var(--df-border)" }}>
              <SectionLabel>Numeric</SectionLabel>
              <div className="font-mono text-sm font-semibold tabular-nums" style={{ color: "var(--df-text)" }}>{numeric}</div>
            </div>
            <div className="rounded-xl px-3.5 py-3" style={{ background: "var(--df-surface)", border: "1px solid var(--df-border)" }}>
              <SectionLabel>Kernel Time</SectionLabel>
              <div className="font-mono text-sm font-semibold tabular-nums" style={{ color: "var(--df-text-dim, #a8acb3)" }}>
                {c.duration_ms != null ? `${Math.round(c.duration_ms)} ms` : "—"}
              </div>
            </div>
          </div>

          {c.error && (
            <div
              className="rounded-xl px-3.5 py-3 font-mono text-[11px]"
              style={{ background: "rgba(207,32,47,0.10)", border: "1px solid rgba(207,32,47,0.28)", color: "var(--df-down, #cf202f)" }}
            >
              {c.error}
            </div>
          )}

          <div className="font-mono text-[10px] pt-1" style={{ color: "var(--df-text-muted, #7c828a)" }}>
            Paste the expression into Wolfram to reproduce this result. That
            round-trip is the proof — symbolic math doesn&apos;t hallucinate.
          </div>
        </div>
      </aside>
    </div>
  );
}
