/**
 * Tolerant client-side CSV → PortfolioPosition parser (ARCHITECTURE.md §8.3 /
 * §10.3). Mirrors the backend `csv_parser.py` contract closely enough that a
 * paste imports cleanly into the rail BEFORE any round-trip:
 *
 *   - sniffs the delimiter (comma / tab / semicolon),
 *   - maps header aliases to canonical fields,
 *   - coerces messy values (strips `$`/`,`, instrument & side synonyms, dates),
 *   - validates each row through ONE Zod ticket schema (DRY),
 *   - never discards a valid row because a sibling row failed,
 *   - returns per-row OK / error results for the import UI.
 *
 * The wire shape is `PortfolioPosition` (snake_case) from `@/types`; this never
 * invents a new shape. Option rows require strike + expiry; equity rows must
 * carry neither (§ rule: option ⇒ strike+expiry, equity ⇒ neither).
 */

import { z } from "zod";

import type { PortfolioPosition } from "@/types";

const MAX_ROWS = 1000;

const DELIMITERS = [",", "\t", ";"] as const;

/** Canonical header → list of accepted aliases (lower-cased, trimmed). */
const HEADER_ALIASES: Record<string, readonly string[]> = {
  symbol: ["symbol", "ticker", "underlying", "sym", "root"],
  instrument: ["instrument", "type", "instrument_type", "kind", "asset"],
  strike: ["strike", "strike_price", "k"],
  expiry: ["expiry", "expiration", "exp", "expiration_date", "expiry_date"],
  quantity: ["quantity", "qty", "size", "contracts", "shares", "position"],
  side: ["side", "direction", "buy_sell", "action"],
  avg_price: [
    "avg_price",
    "price",
    "cost",
    "cost_basis",
    "avg_cost",
    "entry",
    "entry_price",
  ],
};

const CALL_SYNONYMS = new Set(["call", "c", "calls"]);
const PUT_SYNONYMS = new Set(["put", "p", "puts"]);
const EQUITY_SYNONYMS = new Set([
  "equity",
  "stock",
  "share",
  "shares",
  "common",
  "eq",
]);

const SHORT_SYNONYMS = new Set(["short", "sell", "s", "sld", "-", "sell_to_open"]);

export interface CsvRowOk {
  ok: true;
  rowNumber: number;
  raw: Record<string, string>;
  position: PortfolioPosition;
}

export interface CsvRowError {
  ok: false;
  rowNumber: number;
  raw: Record<string, string>;
  message: string;
}

export type CsvRowResult = CsvRowOk | CsvRowError;

export interface CsvParseResult {
  positions: PortfolioPosition[];
  rows: CsvRowResult[];
  okCount: number;
  errorCount: number;
}

function detectDelimiter(headerLine: string): string {
  let best = ",";
  let bestCount = -1;
  for (const delim of DELIMITERS) {
    const count = headerLine.split(delim).length - 1;
    if (count > bestCount) {
      bestCount = count;
      best = delim;
    }
  }
  return best;
}

function splitLine(line: string, delimiter: string): string[] {
  // Minimal quote-aware split; tolerant of stray quotes around values.
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === delimiter && !inQuotes) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out.map((cell) => cell.trim());
}

function buildHeaderIndex(headerCells: string[]): Record<string, number> {
  const index: Record<string, number> = {};
  headerCells.forEach((cell, position) => {
    const normalized = cell.toLowerCase().trim().replace(/\s+/g, "_");
    for (const [canonical, aliases] of Object.entries(HEADER_ALIASES)) {
      if (aliases.includes(normalized) && index[canonical] === undefined) {
        index[canonical] = position;
      }
    }
  });
  return index;
}

function coerceNumber(value: string | undefined): number | null {
  if (value === undefined) return null;
  const cleaned = value.replace(/[$,\s]/g, "");
  if (cleaned === "") return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Normalize many date formats to ISO `YYYY-MM-DD`; returns null if unparseable. */
function coerceDate(value: string | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
  // MM/DD/YYYY or M/D/YY etc.
  const slash = trimmed.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/);
  if (slash) {
    const [, m, d, y] = slash;
    const year = y.length === 2 ? `20${y}` : y;
    return `${year}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
  }
  const parsed = new Date(trimmed);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toISOString().slice(0, 10);
  }
  return null;
}

function coerceInstrument(value: string | undefined): "equity" | "call" | "put" | null {
  if (!value) return null;
  const v = value.toLowerCase().trim();
  if (CALL_SYNONYMS.has(v)) return "call";
  if (PUT_SYNONYMS.has(v)) return "put";
  if (EQUITY_SYNONYMS.has(v)) return "equity";
  return null;
}

/** Raw, pre-validation row shape coerced from the CSV cells. */
const rawTicketSchema = z.object({
  symbol: z.string().min(1).max(8),
  instrument: z.enum(["equity", "call", "put"]),
  strike: z.number().positive().nullable(),
  expiry: z.string().nullable(),
  quantity: z.number().int().refine((q) => q !== 0, "quantity must be non-zero"),
  avg_price: z.number().nonnegative().nullable(),
});

/**
 * The single ticket validator (DRY) — enforces the option⇒strike+expiry /
 * equity⇒neither invariant and emits a canonical `PortfolioPosition`.
 */
function validateTicket(
  raw: z.infer<typeof rawTicketSchema>,
): { position: PortfolioPosition } | { error: string } {
  const isOption = raw.instrument === "call" || raw.instrument === "put";
  if (isOption) {
    if (raw.strike === null) return { error: "option row requires a strike" };
    if (raw.expiry === null) return { error: "option row requires an expiry" };
  } else {
    if (raw.strike !== null) {
      return { error: "equity row must not have a strike" };
    }
    if (raw.expiry !== null) {
      return { error: "equity row must not have an expiry" };
    }
  }
  const position: PortfolioPosition = {
    id: null,
    symbol: raw.symbol.toUpperCase(),
    instrument: raw.instrument,
    strike: raw.strike,
    expiry: raw.expiry,
    quantity: raw.quantity,
    avg_price: raw.avg_price,
    greeks: null,
    wolfram: null,
  };
  return { position };
}

function parseRow(
  cells: string[],
  headerIndex: Record<string, number>,
  rowNumber: number,
  rawRecord: Record<string, string>,
): CsvRowResult {
  const at = (key: string): string | undefined => {
    const idx = headerIndex[key];
    return idx === undefined ? undefined : cells[idx];
  };

  const symbol = at("symbol")?.trim() ?? "";
  const instrument = coerceInstrument(at("instrument"));
  const qtyRaw = coerceNumber(at("quantity"));
  const sideRaw = at("side")?.toLowerCase().trim();

  if (symbol === "") {
    return { ok: false, rowNumber, raw: rawRecord, message: "missing symbol" };
  }
  if (instrument === null) {
    return {
      ok: false,
      rowNumber,
      raw: rawRecord,
      message: `unknown instrument "${at("instrument") ?? ""}"`,
    };
  }
  if (qtyRaw === null) {
    return { ok: false, rowNumber, raw: rawRecord, message: "missing/invalid quantity" };
  }

  // Side synonym applies a sign to an unsigned magnitude; an explicit negative
  // quantity is respected as-is.
  let quantity = Math.trunc(qtyRaw);
  if (sideRaw && SHORT_SYNONYMS.has(sideRaw) && quantity > 0) {
    quantity = -quantity;
  }

  const parsed = rawTicketSchema.safeParse({
    symbol,
    instrument,
    strike: coerceNumber(at("strike")),
    expiry: coerceDate(at("expiry")),
    quantity,
    avg_price: coerceNumber(at("avg_price")),
  });

  if (!parsed.success) {
    return {
      ok: false,
      rowNumber,
      raw: rawRecord,
      message: parsed.error.issues[0]?.message ?? "invalid row",
    };
  }

  const result = validateTicket(parsed.data);
  if ("error" in result) {
    return { ok: false, rowNumber, raw: rawRecord, message: result.error };
  }
  return { ok: true, rowNumber, raw: rawRecord, position: result.position };
}

/**
 * Parse pasted CSV text into per-row results. Tolerant: a malformed row is
 * rejected with a message but never aborts the whole import.
 */
export function parseCsv(text: string): CsvParseResult {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trimEnd())
    .filter((l) => l.trim() !== "");

  if (lines.length === 0) {
    return { positions: [], rows: [], okCount: 0, errorCount: 0 };
  }

  const delimiter = detectDelimiter(lines[0]);
  const headerCells = splitLine(lines[0], delimiter);
  const headerIndex = buildHeaderIndex(headerCells);

  const rows: CsvRowResult[] = [];
  const bodyLines = lines.slice(1).slice(0, MAX_ROWS);

  bodyLines.forEach((line, i) => {
    const cells = splitLine(line, delimiter);
    const rawRecord: Record<string, string> = {};
    headerCells.forEach((h, idx) => {
      rawRecord[h || `col_${idx}`] = cells[idx] ?? "";
    });
    rows.push(parseRow(cells, headerIndex, i + 2, rawRecord));
  });

  const positions = rows.filter((r): r is CsvRowOk => r.ok).map((r) => r.position);
  const okCount = positions.length;
  return {
    positions,
    rows,
    okCount,
    errorCount: rows.length - okCount,
  };
}
