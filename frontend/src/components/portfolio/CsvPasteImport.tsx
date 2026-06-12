"use client";

/**
 * CsvPasteImport — tolerant CSV-paste import for the rail (ARCHITECTURE.md
 * §8.3 / §10.3). Parsing happens client-side via `lib/portfolio/parseCsv.ts`;
 * each row gets an OK / error badge so the user sees exactly what imported and
 * why anything was rejected. Valid rows are never discarded because a sibling
 * row failed. Only the OK rows are committed to client state.
 */

import { useMemo, useState } from "react";

import { parseCsv, type CsvParseResult } from "@/lib/portfolio/parseCsv";
import type { PortfolioPosition } from "@/types";

interface CsvPasteImportProps {
  onImport: (positions: PortfolioPosition[]) => void;
}

const ACCENT = "var(--df-accent, #f5a623)";
const UP = "var(--df-up, #05b169)";
const DOWN = "var(--df-down, #cf202f)";
const MUTED = "var(--df-text-muted, #7c828a)";
const DIM = "var(--df-text-dim, #a8acb3)";

const PLACEHOLDER =
  "symbol,instrument,quantity,strike,expiry,price\nSPY,call,2,450,2026-07-18,7.75\nAAPL,equity,100,,,190.20";

export function CsvPasteImport({ onImport }: CsvPasteImportProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");

  const result: CsvParseResult | null = useMemo(
    () => (text.trim() === "" ? null : parseCsv(text)),
    [text],
  );

  const handleImport = () => {
    if (!result || result.okCount === 0) return;
    onImport(result.positions);
    setText("");
    setOpen(false);
  };

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between font-mono text-[10px] font-bold uppercase tracking-widest py-2 px-2.5 rounded-md transition-colors"
        style={{ background: "var(--df-surface)", color: MUTED, border: "1px solid var(--df-border-strong)", letterSpacing: "0.1em" }}
        aria-expanded={open}
      >
        <span>Paste CSV</span>
        <span style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 150ms" }}>▾</span>
      </button>

      {open && (
        <div className="space-y-2">
          <textarea
            aria-label="CSV positions"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={PLACEHOLDER}
            rows={5}
            className="w-full font-mono text-[10px] leading-relaxed px-2.5 py-2 rounded-md outline-none resize-y"
            style={{ background: "rgba(0,0,0,0.30)", border: "1px solid var(--df-border-strong)", color: DIM }}
          />

          {result && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-3 font-mono text-[10px]">
                <span style={{ color: UP }}>✓ {result.okCount} ok</span>
                {result.errorCount > 0 && <span style={{ color: DOWN }}>✕ {result.errorCount} rejected</span>}
              </div>

              <div className="max-h-[140px] overflow-y-auto space-y-1">
                {result.rows.map((row) => (
                  <div
                    key={row.rowNumber}
                    className="flex items-center gap-2 px-2 py-1 rounded-md font-mono text-[9px]"
                    style={{
                      background: row.ok ? "rgba(5,177,105,0.06)" : "rgba(207,32,47,0.06)",
                      border: `1px solid ${row.ok ? "rgba(5,177,105,0.18)" : "rgba(207,32,47,0.18)"}`,
                    }}
                  >
                    <span style={{ color: row.ok ? UP : DOWN, fontWeight: 700 }}>
                      {row.ok ? "OK" : "ERR"}
                    </span>
                    <span className="truncate" style={{ color: DIM }}>
                      {row.ok
                        ? `${row.position.symbol} ${row.position.instrument} ${row.position.quantity}`
                        : `row ${row.rowNumber}: ${row.message}`}
                    </span>
                  </div>
                ))}
              </div>

              <button
                type="button"
                onClick={handleImport}
                disabled={result.okCount === 0}
                className="w-full font-mono text-[11px] font-bold uppercase tracking-widest py-2 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: "rgba(245,166,35,0.18)", color: ACCENT, border: "1px solid rgba(245,166,35,0.32)", letterSpacing: "0.1em" }}
              >
                Import {result.okCount} {result.okCount === 1 ? "Position" : "Positions"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
