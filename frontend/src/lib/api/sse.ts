/**
 * SSE consumer for GET /analyze/stream (ARCHITECTURE.md §6 + §10.2).
 *
 * `/analyze/stream` is a GET endpoint, so the browser-native `EventSource` is
 * viable (and gives free reconnection + heartbeat handling). Each named frame
 * is dispatched to a typed handler; the caller Zod-parses the payload (fail
 * loud). The reducer in `useAnalysisStream` is out-of-order safe; the `done`
 * event carries the authoritative full `AnalyzeResponse`.
 */

import { getApiBaseUrl } from "@/lib/api/client";

/** Named SSE events from §6 (in emit order). */
export type SseEventName =
  | "stage"
  | "market"
  | "portfolio"
  | "wolfram"
  | "hedge"
  | "scenario"
  | "summary"
  | "engine"
  | "done"
  | "error";

const SSE_EVENT_NAMES: readonly SseEventName[] = [
  "stage",
  "market",
  "portfolio",
  "wolfram",
  "hedge",
  "scenario",
  "summary",
  "engine",
  "done",
  "error",
];

export interface StreamHandlers {
  /** Raw parsed JSON for the named event. Caller validates with Zod. */
  onEvent: (name: SseEventName, data: unknown) => void;
  /** Transport-level failure (network/parse). Distinct from an `error` frame. */
  onTransportError: (error: Error) => void;
}

export interface StreamParams {
  symbol: string;
  dteMax: number;
  portfolioId?: string;
}

export interface StreamConnection {
  close: () => void;
}

function buildStreamUrl(params: StreamParams): string {
  const search = new URLSearchParams({
    symbol: params.symbol,
    dte_max: String(params.dteMax),
  });
  if (params.portfolioId) {
    search.set("portfolio_id", params.portfolioId);
  }
  return `${getApiBaseUrl()}/analyze/stream?${search.toString()}`;
}

function safeParse(raw: string): unknown {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

/**
 * Opens an EventSource against `/analyze/stream` and dispatches each named
 * frame. Returns a handle whose `close()` tears down the connection. The UI
 * should close on `done`/`error`.
 */
export function openAnalysisStream(
  params: StreamParams,
  handlers: StreamHandlers,
): StreamConnection {
  const source = new EventSource(buildStreamUrl(params));

  const listeners = SSE_EVENT_NAMES.map((name) => {
    const listener = (event: MessageEvent<string>) => {
      handlers.onEvent(name, safeParse(event.data));
    };
    source.addEventListener(name, listener as EventListener);
    return { name, listener };
  });

  // `error` here is the EventSource transport error, not a §6 `error` frame.
  const onError = () => {
    // EventSource fires `error` on normal close after the server ends the
    // stream; only surface it while the connection is still trying to open.
    if (source.readyState === EventSource.CLOSED) {
      return;
    }
    handlers.onTransportError(new Error("Stream connection failed"));
  };
  source.addEventListener("error", onError);

  return {
    close: () => {
      for (const { name, listener } of listeners) {
        source.removeEventListener(name, listener as EventListener);
      }
      source.removeEventListener("error", onError);
      source.close();
    },
  };
}
