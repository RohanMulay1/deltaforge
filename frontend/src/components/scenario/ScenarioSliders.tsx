"use client";

/**
 * ScenarioSliders — spot% / IV% / DTE controls for the scenario panel
 * (ARCHITECTURE.md §10.3, P2). The parent debounces the resulting POST
 * /scenario (~200ms) in `useScenarioPnl`; these sliders just emit immediate
 * control changes. Terminal palette, monospace numerics.
 */

import type { ScenarioControls } from "@/hooks/useScenarioPnl";

interface ScenarioSlidersProps {
  controls: ScenarioControls;
  onChange: (next: ScenarioControls) => void;
}

const ACCENT = "var(--df-accent, #f5a623)";
const MUTED = "var(--df-text-muted, #7c828a)";

interface SliderRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}

function SliderRow({ label, value, min, max, step, format, onChange }: SliderRowProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: MUTED, letterSpacing: "0.1em" }}>
          {label}
        </span>
        <span className="font-mono text-xs font-semibold tabular-nums" style={{ color: ACCENT }}>
          {format(value)}
        </span>
      </div>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full df-range"
        style={{ accentColor: "#f5a623" }}
      />
    </div>
  );
}

export function ScenarioSliders({ controls, onChange }: ScenarioSlidersProps) {
  const patch = (partial: Partial<ScenarioControls>) =>
    onChange({ ...controls, ...partial });

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <SliderRow
        label="Spot Range ±"
        value={controls.spotSpanPct}
        min={5}
        max={40}
        step={1}
        format={(v) => `±${v}%`}
        onChange={(v) => patch({ spotSpanPct: v })}
      />
      <SliderRow
        label="IV Shift ±"
        value={controls.ivSpanPct}
        min={5}
        max={50}
        step={1}
        format={(v) => `±${v}%`}
        onChange={(v) => patch({ ivSpanPct: v })}
      />
      <SliderRow
        label="DTE Override"
        value={controls.dteOverride ?? 0}
        min={0}
        max={90}
        step={1}
        format={(v) => (v === 0 ? "near" : `${v}d`)}
        onChange={(v) => patch({ dteOverride: v === 0 ? null : v })}
      />
    </div>
  );
}
