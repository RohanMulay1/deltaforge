"use client";

/**
 * AddPositionTicket — the manual leg-entry form (ARCHITECTURE.md §10.3). Zod
 * enforces the canonical invariant: an option requires strike + expiry, an
 * equity must have neither. On submit it emits a canonical `PortfolioPosition`
 * (snake_case) and clears the option-only fields.
 *
 * The signed quantity carries the long/short direction (no separate `side`
 * crosses the wire — §1 rule 6); a "SHORT" toggle just negates the magnitude.
 */

import { useMemo, useState } from "react";

import { z } from "zod";

import type { PortfolioPosition } from "@/types";

interface AddPositionTicketProps {
  onAdd: (position: PortfolioPosition) => void;
}

type Instrument = "equity" | "call" | "put";

const ACCENT = "var(--df-accent, #f5a623)";
const DOWN = "var(--df-down, #cf202f)";
const MUTED = "var(--df-text-muted, #7c828a)";

const fieldStyle: React.CSSProperties = {
  background: "var(--df-surface)",
  border: "1px solid var(--df-border-strong)",
  color: "var(--df-text)",
};

const ticketSchema = z
  .object({
    symbol: z
      .string()
      .trim()
      .min(1, "symbol required")
      .max(8, "symbol too long")
      .regex(/^[A-Za-z.\-]+$/, "invalid symbol"),
    instrument: z.enum(["equity", "call", "put"]),
    quantity: z
      .number({ invalid_type_error: "quantity required" })
      .int("whole contracts only")
      .refine((q) => q !== 0, "quantity must be non-zero"),
    strike: z.number().positive("strike must be > 0").nullable(),
    expiry: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/, "expiry must be YYYY-MM-DD")
      .nullable(),
    avg_price: z.number().nonnegative("price must be ≥ 0").nullable(),
  })
  .superRefine((data, ctx) => {
    const isOption = data.instrument === "call" || data.instrument === "put";
    if (isOption) {
      if (data.strike === null) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["strike"], message: "option requires a strike" });
      }
      if (data.expiry === null) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["expiry"], message: "option requires an expiry" });
      }
    } else {
      if (data.strike !== null) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["strike"], message: "equity must not have a strike" });
      }
      if (data.expiry !== null) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["expiry"], message: "equity must not have an expiry" });
      }
    }
  });

function num(value: string): number | null {
  const cleaned = value.replace(/[$,\s]/g, "");
  if (cleaned === "") return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

export function AddPositionTicket({ onAdd }: AddPositionTicketProps) {
  const [symbol, setSymbol] = useState("");
  const [instrument, setInstrument] = useState<Instrument>("call");
  const [qty, setQty] = useState("");
  const [isShort, setIsShort] = useState(false);
  const [strike, setStrike] = useState("");
  const [expiry, setExpiry] = useState("");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isOption = instrument === "call" || instrument === "put";

  const reset = () => {
    setSymbol("");
    setQty("");
    setStrike("");
    setExpiry("");
    setPrice("");
    setIsShort(false);
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const magnitude = num(qty);
    const signedQty =
      magnitude === null ? null : Math.trunc(isShort ? -Math.abs(magnitude) : Math.abs(magnitude));

    const parsed = ticketSchema.safeParse({
      symbol,
      instrument,
      quantity: signedQty ?? Number.NaN,
      strike: isOption ? num(strike) : null,
      expiry: isOption ? (expiry.trim() === "" ? null : expiry.trim()) : null,
      avg_price: num(price),
    });

    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "invalid position");
      return;
    }

    const data = parsed.data;
    const position: PortfolioPosition = {
      id: null,
      symbol: data.symbol.toUpperCase(),
      instrument: data.instrument,
      strike: data.strike,
      expiry: data.expiry,
      quantity: data.quantity,
      avg_price: data.avg_price,
      greeks: null,
      wolfram: null,
    };
    onAdd(position);
    reset();
  };

  const instrumentTabs = useMemo<Instrument[]>(() => ["call", "put", "equity"], []);

  return (
    <form onSubmit={handleSubmit} className="space-y-2.5">
      <span className="font-mono text-[9px] font-bold uppercase tracking-widest" style={{ color: MUTED, letterSpacing: "0.12em" }}>
        Add Position
      </span>

      {/* Instrument tabs */}
      <div className="grid grid-cols-3 gap-1.5">
        {instrumentTabs.map((opt) => {
          const active = instrument === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => setInstrument(opt)}
              className="font-mono text-[10px] font-bold uppercase py-1.5 rounded-md transition-colors"
              style={{
                background: active ? "rgba(245,166,35,0.16)" : "var(--df-surface)",
                color: active ? ACCENT : MUTED,
                border: `1px solid ${active ? "rgba(245,166,35,0.30)" : "var(--df-border-strong)"}`,
              }}
            >
              {opt}
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <input
          aria-label="Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="SYMBOL"
          className="font-mono text-xs uppercase px-2.5 py-2 rounded-md outline-none"
          style={fieldStyle}
        />
        <div className="flex items-stretch gap-1.5">
          <input
            aria-label="Quantity"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="QTY"
            inputMode="numeric"
            className="font-mono text-xs px-2.5 py-2 rounded-md outline-none flex-1 min-w-0"
            style={fieldStyle}
          />
          <button
            type="button"
            onClick={() => setIsShort((s) => !s)}
            aria-pressed={isShort}
            className="font-mono text-[9px] font-bold uppercase px-2 rounded-md transition-colors"
            style={{
              background: isShort ? "rgba(207,32,47,0.14)" : "var(--df-surface)",
              color: isShort ? DOWN : MUTED,
              border: `1px solid ${isShort ? "rgba(207,32,47,0.30)" : "var(--df-border-strong)"}`,
            }}
          >
            {isShort ? "SHORT" : "LONG"}
          </button>
        </div>
      </div>

      {isOption && (
        <div className="grid grid-cols-2 gap-2">
          <input
            aria-label="Strike"
            value={strike}
            onChange={(e) => setStrike(e.target.value)}
            placeholder="STRIKE"
            inputMode="decimal"
            className="font-mono text-xs px-2.5 py-2 rounded-md outline-none"
            style={fieldStyle}
          />
          <input
            aria-label="Expiry"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            placeholder="YYYY-MM-DD"
            className="font-mono text-xs px-2.5 py-2 rounded-md outline-none"
            style={fieldStyle}
          />
        </div>
      )}

      <input
        aria-label="Average price"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        placeholder="AVG PRICE (optional)"
        inputMode="decimal"
        className="font-mono text-xs px-2.5 py-2 rounded-md outline-none w-full"
        style={fieldStyle}
      />

      {error && (
        <div className="font-mono text-[10px]" style={{ color: DOWN }}>
          {error}
        </div>
      )}

      <button
        type="submit"
        className="w-full font-mono text-[11px] font-bold uppercase tracking-widest py-2 rounded-md transition-colors"
        style={{ background: "rgba(245,166,35,0.18)", color: ACCENT, border: "1px solid rgba(245,166,35,0.32)", letterSpacing: "0.1em" }}
      >
        + Add Leg
      </button>
    </form>
  );
}
