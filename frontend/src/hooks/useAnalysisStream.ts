"use client";

/**
 * useAnalysisStream — consumes GET /analyze/stream and assembles the §6 events
 * into one `AnalysisResult` in the React Query cache (ARCHITECTURE.md §10.2).
 *
 * - Each frame is Zod-parsed (fail loud); a bad frame surfaces as an error.
 * - The reducer is out-of-order safe; the `done` event is authoritative and
 *   replaces the partial with the full canonical `AnalyzeResponse`.
 * - Per-stage `StageStatus` (idle|loading|ready|error) drives `<PanelState>`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import {
  analyzeResponseSchema,
  engineStatusSchema,
  hedgeRecommendationSchema,
  marketSnapshotSchema,
  portfolioGreeksSchema,
  scenarioSurfaceSchema,
  stageEventSchema,
  summaryEventSchema,
  wolframComputationSchema,
} from "@/lib/api/schemas";
import { openAnalysisStream, type SseEventName } from "@/lib/api/sse";
import { analysisQueryKey, STAGE_NAMES } from "@/lib/query/queryClient";
import type {
  AnalysisResult,
  StageName,
  StageStatus,
  WolframComputation,
} from "@/types";

export type StageMap = Record<StageName, StageStatus>;

function idleStages(): StageMap {
  return STAGE_NAMES.reduce<StageMap>((acc, name) => {
    acc[name] = "idle";
    return acc;
  }, {} as StageMap);
}

/** A partial accumulator that fills as events stream in. */
type PartialAnalysis = Partial<AnalysisResult> & {
  wolfram_computations?: WolframComputation[];
};

export interface UseAnalysisStreamResult {
  start: (symbol: string, dteMax: number) => void;
  stop: () => void;
  data: AnalysisResult | null;
  partial: PartialAnalysis | null;
  stages: StageMap;
  isStreaming: boolean;
  error: string | null;
  symbol: string | null;
  dteMax: number | null;
}

export function useAnalysisStream(): UseAnalysisStreamResult {
  const queryClient = useQueryClient();
  const connectionRef = useRef<{ close: () => void } | null>(null);
  const partialRef = useRef<PartialAnalysis>({});

  const [partial, setPartial] = useState<PartialAnalysis | null>(null);
  const [data, setData] = useState<AnalysisResult | null>(null);
  const [stages, setStages] = useState<StageMap>(idleStages);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [symbol, setSymbol] = useState<string | null>(null);
  const [dteMax, setDteMax] = useState<number | null>(null);

  const closeConnection = useCallback(() => {
    connectionRef.current?.close();
    connectionRef.current = null;
  }, []);

  const stop = useCallback(() => {
    closeConnection();
    setIsStreaming(false);
  }, [closeConnection]);

  useEffect(() => closeConnection, [closeConnection]);

  const start = useCallback(
    (nextSymbol: string, nextDteMax: number) => {
      closeConnection();

      partialRef.current = {};
      setPartial({});
      setData(null);
      setStages(idleStages());
      setError(null);
      setIsStreaming(true);
      setSymbol(nextSymbol);
      setDteMax(nextDteMax);

      const markStage = (stage: StageName, status: StageStatus) => {
        setStages((prev) =>
          prev[stage] === status ? prev : { ...prev, [stage]: status },
        );
      };

      const commitPartial = (patch: PartialAnalysis) => {
        partialRef.current = { ...partialRef.current, ...patch };
        setPartial(partialRef.current);
      };

      const handleEvent = (name: SseEventName, raw: unknown) => {
        switch (name) {
          case "stage": {
            const evt = stageEventSchema.parse(raw);
            const status: StageStatus =
              evt.status === "done"
                ? "ready"
                : evt.status === "error"
                  ? "error"
                  : "loading";
            markStage(evt.stage, status);
            break;
          }
          case "market": {
            const market = marketSnapshotSchema.parse(raw);
            commitPartial({
              market,
              symbol: market.symbol,
              spot_price: market.spot_price,
              expiry: market.expiry_used,
              calls_count: market.calls_count,
              puts_count: market.puts_count,
              order_flow_imbalance: market.order_flow_imbalance,
              pin_risk_score: market.pin_risk_score,
              iv_rank: market.iv_stats.iv_rank,
              options_chain: market.chain,
            });
            markStage("market_data", "ready");
            break;
          }
          case "portfolio": {
            commitPartial({ portfolio_greeks: portfolioGreeksSchema.parse(raw) });
            markStage("portfolio", "ready");
            break;
          }
          case "wolfram": {
            const computation = wolframComputationSchema.parse(raw);
            const existing = partialRef.current.wolfram_computations ?? [];
            commitPartial({
              wolfram_computations: [...existing, computation],
            });
            break;
          }
          case "hedge": {
            commitPartial({ hedge: hedgeRecommendationSchema.parse(raw) });
            markStage("hedge", "ready");
            break;
          }
          case "scenario": {
            commitPartial({ scenario: scenarioSurfaceSchema.parse(raw) });
            markStage("scenario", "ready");
            break;
          }
          case "summary": {
            const evt = summaryEventSchema.parse(raw);
            commitPartial({ risk_summary: evt.risk_summary });
            markStage("summary", "ready");
            break;
          }
          case "engine": {
            commitPartial({ engine_status: engineStatusSchema.parse(raw) });
            break;
          }
          case "done": {
            const full = analyzeResponseSchema.parse(raw);
            partialRef.current = full;
            setPartial(full);
            setData(full);
            queryClient.setQueryData(
              analysisQueryKey(nextSymbol, nextDteMax),
              full,
            );
            setStages((prev) => {
              const next = { ...prev };
              for (const stage of STAGE_NAMES) {
                if (next[stage] !== "error") {
                  next[stage] = "ready";
                }
              }
              return next;
            });
            setIsStreaming(false);
            closeConnection();
            break;
          }
          case "error": {
            const detail =
              raw && typeof raw === "object" && "detail" in raw
                ? String((raw as { detail: unknown }).detail)
                : "Analysis stream error";
            setError(detail);
            setIsStreaming(false);
            closeConnection();
            break;
          }
        }
      };

      connectionRef.current = openAnalysisStream(
        { symbol: nextSymbol, dteMax: nextDteMax },
        {
          onEvent: (name, payload) => {
            try {
              handleEvent(name, payload);
            } catch (err) {
              setError(
                err instanceof Error
                  ? `Invalid ${name} frame: ${err.message}`
                  : `Invalid ${name} frame`,
              );
              setIsStreaming(false);
              closeConnection();
            }
          },
          onTransportError: (transportError) => {
            setError(transportError.message);
            setIsStreaming(false);
            closeConnection();
          },
        },
      );
    },
    [closeConnection, queryClient],
  );

  return {
    start,
    stop,
    data,
    partial,
    stages,
    isStreaming,
    error,
    symbol,
    dteMax,
  };
}
