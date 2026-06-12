# DeltaForge — Build Plan

> Ordered, dependency-aware plan in **disjoint workstreams**. Each workstream owns a non-overlapping set of files/directories so parallel implementation agents do not conflict. The canonical contract is `docs/ARCHITECTURE.md` — all field names come from there. Where two workstreams must touch the same file, that file is assigned to exactly ONE owner and the other consumes it via the contract (called out as an **integration checkpoint**).

## Legend
- 🔑 = requires a live resource (the **local Wolfram Engine kernel**, or `DATABASE_URL`) for full verification. The Wolfram kernel is already installed + activated locally, so W-KEY is satisfied on this host; until `DATABASE_URL` lands, DB workstreams are verified against mocks/fallback.
- ⛓ = integration checkpoint (cross-workstream handoff).

## Critical path (must land in order)
```
WS0 (contract + Wolfram skeleton)  ──►  WS1 (providers/domain)  ──►  WS2 (pipeline+SSE)
        │                                      │                          │
        ├──► WS5 (frontend contract+data layer) depends on WS0 only       │
        │                                                                  ▼
        └──► WS3 (persistence) ── parallel ──►  WS4 (ops/alerts) ──► WS6 (frontend P2 panels)
```
**WS0 lands first** — everything depends on the canonical Pydantic models + the WolframService skeleton/DTOs.

---

## WS0 — Canonical data contract + WolframService skeleton  (P0)  🔑
**Owns:**
- `backend/models/schemas_common.py`, `schemas_greeks.py`, `schemas_wolfram.py`, `schemas_market.py`, `schemas_portfolio.py`, `schemas_hedge.py`, `schemas_scenario.py`, `schemas_analyze.py`, `schemas_requests.py`
- `backend/models/__init__.py` (re-exports; old `schemas.py` kept as a thin shim re-exporting new names, then deleted in WS2)
- `backend/services/wolfram/` (all: `__init__.py`, `service.py`, `session_pool.py`, `expressions.py`, `fallback.py`, `cache.py`, `dto.py`)
- `backend/core/wolfram_settings.py`
- `backend/errors.py` (domain exception taxonomy + `ErrorEnvelope`, `FieldError`)

**Modifies:** `backend/main.py` (only: register exception handlers + mount a real `/health` and `/health/wolfram`; wire `WolframService` into lifespan). `backend/requirements.txt` (add `wolframclient`, `scipy`, `numpy`, `mpmath`).

**Deletes:** `backend/agents/wolfram_risk_agent.py` (WL builders ported into `expressions.py` first).

**Acceptance:**
- All Pydantic models import, are `frozen=True, extra="forbid"`, round-trip JSON.
- `WolframService` constructs with NO kernel (binary absent or `wolframclient` missing) → starts in `numeric_fallback`; `health()` returns `EngineStatus{wolfram_available:false, engine_in_use:"numeric_fallback", reason:"kernel_unavailable"}`.
- `contract_greeks`, `portfolio_greeks`, `delta_neutral_hedge`, `pnl_surface` all return valid DTOs via `fallback.py`, each carrying `wl_input` (the expression that *would* run) and `engine:"numeric_fallback"`.
- Unit test asserts NO fallback path can emit `WOLFRAM_CLOUD`; parity test (numeric path internally self-consistent).
- `/health` + `/health/wolfram` respond.

**⛓ Wolfram-kernel checkpoint (W-KEY):** with the **local Wolfram Engine kernel** installed + activated (already true on this host; `WOLFRAM_KERNEL_PATH` overrides the default `WolframKernel.exe` location), `health()` canary `1+1` returns verified `2`, `engine_in_use:"wolfram"`; a `contract_greeks` call returns `result_raw` that pastes back into Wolfram and reproduces. **W-KEY is satisfied by the local kernel — no cloud keys are required.** Workstreams still build and test fully against the labeled fallback on any host without the kernel.

---

## WS1 — MarketDataProvider + Portfolio domain  (P0/P1)
**Depends on:** WS0 (imports `Greeks`, `PortfolioPosition`, `InstrumentType`, `OptionType` from models; calls `WolframService` interface).
**Owns:**
- `backend/providers/` — `base.py`, `yfinance_provider.py`, `cache.py`, `retry.py`, `errors.py`, `factory.py`
- `backend/analytics.py` (OFI + pin_risk, extracted)
- `backend/domain/` — `portfolio.py`, `greeks_aggregation.py`, `hedging.py`
- `backend/domain/ingestion/` — `ticket.py`, `csv_parser.py`, `aliases.py`

**Deletes/refactors:** `backend/agents/market_data_agent.py` → split into `YFinanceProvider` (fetch only) + `analytics.py` (OFI/pin). Remove `time.sleep` retry.

**Acceptance:**
- `YFinanceProvider` runs all yfinance calls via `run_in_executor` (no event-loop block); `RetryPolicy` uses `asyncio.sleep`.
- `CachingProvider` TTLs (spot 5s / chain 30s / exp 1h), single-flight per key.
- `aggregate_portfolio_greeks` pure unit tests: long 5 ATM calls (0.5Δ) ⇒ +250 net delta; short positions subtract; equity multiplier 1 vs option 100.
- `hedging.delta_to_hedge = HEDGE_TARGET_DELTA - net_delta`; empty portfolio ⇒ no hedge; multi-symbol groups by underlying.
- CSV parser: per-row `CsvRowError`, valid rows survive sibling failures, tab/comma/semicolon sniffing, alias + date coercion, 1000-row cap.
- `PositionTicket` validation (option⇒strike+expiry, equity⇒neither, expiry-not-past).

**⛓ checkpoint P-DOM:** WS1's `Position`→`PortfolioPosition` serialization (signed `quantity`, no `side` on wire) verified against WS0 schema.

---

## WS2 — LangGraph pipeline + SSE assembly + analyze routers  (P0/P1)  🔑
**Depends on:** WS0 (models, WolframService), WS1 (provider, domain, analytics).
**Owns:**
- `backend/graph/pipeline.py`, `backend/graph/state.py` (rewrite: nodes `market_data → greeks → portfolio → hedge → scenario → summary`; `GraphState` gains `iv_stats, portfolio_greeks, scenario, wolfram_computations`)
- `backend/graph/nodes/` (one file per node if pipeline.py exceeds 800 lines)
- `backend/routers/analyze.py` (POST `/analyze`, GET `/analyze/stream`, POST `/portfolio/greeks`)
- `backend/sse.py` (SSE framing helper + event reducer contract)

**Modifies:** `backend/main.py` (mount `analyze` router; assemble `AnalyzeResponse`). Deletes the old `schemas.py` shim. Wires the scenario node to return a `ScenarioSurface{is_stub:true}` in P0, real Wolfram surface in P2.

**Acceptance:**
- POST `/analyze` returns a full `AnalyzeResponse` — `iv_rank`, `portfolio_greeks`, `options_chain` all populated on live data (no zeros).
- GET `/analyze/stream` emits the §6 event sequence; `done` payload equals the non-stream `/analyze`. Out-of-order safe; 15s heartbeat.
- Wolfram failure degrades to `numeric_fallback` without 500; `engine_status` honest.
- `/portfolio/greeks` returns aggregate `PortfolioGreeks` for posted positions.

**⛓ checkpoint API-LIVE:** consumed by W-KEY (Wolfram) — with the local kernel running, every `WolframComputation.engine` in the response is `wolfram` and `wolfram_computations[]` is non-empty.

---

## WS3 — Persistence (Postgres + repositories + Alembic)  (P3)  🔑
**Depends on:** WS0 (JSONB payload shapes mirror `AnalyzeResponse`/`HedgeRecommendation`/`PortfolioGreeks`). Independent of WS1/WS2 file-wise.
**Owns:**
- `backend/db/` — `base.py`, `session.py`, `models/{__init__,portfolio,position,saved_analysis,watchlist,alert}.py`, `repositories/{base,portfolio_repo,position_repo,analysis_repo,watchlist_repo,alert_repo}.py`
- `backend/alembic/` (`env.py`, `versions/0001_initial_schema.py`)
- `backend/core/settings.py`, `core/cors.py`, `core/ratelimit.py`, `core/logging.py`
- `backend/routers/portfolios.py`, `watchlist.py`, `history.py`

**Modifies:** `backend/main.py` (router decomposition: include `portfolios/watchlist/history`; CORS from env; slowapi limiter; relocate logging). `requirements.txt` (`sqlalchemy[asyncio]`, `asyncpg`, `psycopg`, `alembic`, `slowapi`, `apscheduler`, `pydantic-settings`).

**Acceptance:**
- 8 tables created via Alembic 0001; `engine_mode` CHECK ∈ `{wolfram, numeric_fallback}` (canonical enum — NOT `scipy_fallback`/`wolfram_cloud`).
- Every table has nullable indexed `user_id`. `saved_analyses` + `alert_events` repos have no update/delete.
- Repos `flush` not `commit`; `get_session` commits at request end / rolls back on error.
- `/analyze` persists exactly one `SavedAnalysis` with correct `engine_mode`.
- CORS rejects disallowed origin; rate limiter returns 429 after configured count; settings fail-fast on missing secret.

**⛓ checkpoint DB-KEY:** requires `DATABASE_URL` (hosted Postgres). `alembic upgrade head` succeeds; JSONB round-trips. SQLite-on-aiosqlite covers pure CRUD; JSONB-touching tests pin to Postgres.

---

## WS4 — Ops: background alert re-evaluation  (P3)
**Depends on:** WS2 (reuses pipeline for re-eval), WS3 (alert repos, session).
**Owns:**
- `backend/ops/scheduler.py`, `backend/ops/alert_evaluator.py`
- `backend/routers/alerts.py`

**Modifies:** `backend/main.py` (start/stop scheduler in lifespan; include `alerts` router).

**Acceptance:**
- APScheduler `AsyncIOScheduler` (`max_instances=1, coalesce=True, jitter=15`).
- `evaluate_all_alerts` groups by symbol (no N+1), respects `cooldown_seconds`, writes `AlertEvent` linked to a real `saved_analyses` row, records honest `engine_mode`.
- `_check` logic: `delta_drift` (|delta−target|>tolerance), `pin_risk` (score≥threshold ∧ dte≤window), `gamma_spike` (|gamma|≥threshold). Unit-tested ≥90%.
- One symbol's failure does not abort the sweep.

---

## WS5 — Frontend contract + data layer + honest dashboard  (P0/P1)
**Depends on:** WS0 contract only (does NOT need the backend running — Zod schemas + fixture suffice for build; `analyze()` non-stream path tested against fixture).
**Owns:**
- `frontend/src/lib/api/` — `client.ts`, `sse.ts`, `schemas.ts` (Zod, **snake_case**, single source of truth)
- `frontend/src/lib/query/queryClient.ts`
- `frontend/src/hooks/` — `useAnalysisStream.ts`, `usePanelStatus.ts`, `useWolframHealth.ts`
- `frontend/src/components/feedback/` — `Skeleton.tsx`, `PanelState.tsx`, `EmptyState.tsx` + per-panel skeletons
- `frontend/src/components/status/SymbolicEngineBadge.tsx`
- `frontend/src/components/chain/useChainRows.ts`
- `frontend/src/__fixtures__/analysis.fixture.ts`

**Modifies:** `frontend/src/types/index.ts` (re-export `z.infer`); `app/page.tsx` (shell + stream-driven, remove `previewMode`/`MOCK_DATA`); `app/layout.tsx` (QueryClientProvider); `AnalyzeForm.tsx` (use hook); `Header.tsx` (`SymbolicEngineBadge`); `OptionsChainTable.tsx` (virtualize + ATM + delta); `HUDCards.tsx`, `IVSurfacePlot.tsx`, `HedgePanel.tsx` (real data, import `@/types`); `globals.css` (color tokens); `.eslintrc` (ban `__fixtures__` import from app/components).

**Deletes:** `frontend/src/lib/mock-data.ts`; `components/RiskDashboard.tsx`; `components/HedgeCard.tsx` (confirm no imports first).

**New deps:** `@tanstack/react-query`, `@tanstack/react-virtual`, `zod`.

**Acceptance:**
- `MOCK_DATA` has no runtime path; ESLint blocks fixture imports from app/components.
- On live data, all 5 HUD cards + chain + IV surface render real values (no zeros). Per-panel 4-state (idle/loading/ready/error); skeletons shape-matched (CLS<0.1).
- `useAnalysisStream` assembles SSE events into one `AnalysisResult` in React Query; panels fill top-down.
- `SymbolicEngineBadge` reflects `/health/wolfram` (green wolfram / amber numeric_fallback / gray checking).
- Chain virtualized + ATM-anchored at 200+ rows.

**⛓ checkpoint FE-API:** point `NEXT_PUBLIC_API_URL` at WS2 backend; the streamed `done` payload validates against the Zod `AnalyzeResponse` schema (field names must match §4 exactly — the contract conformance gate).

---

## WS6 — Frontend P1 rail + P2 scenario/explain panels  (P1/P2)  🔑
**Depends on:** WS5 (data layer, types, shell), WS2 (`/portfolio/greeks`, `/scenario`), W-KEY for live Wolfram values.
**Owns:**
- `frontend/src/components/portfolio/` — `PortfolioRail.tsx`, `AggregateGreeks.tsx`, `PositionsList.tsx`, `PositionRow.tsx`, `AddPositionTicket.tsx`, `CsvPasteImport.tsx`
- `frontend/src/components/scenario/` — `ScenarioPanel.tsx`, `ScenarioSliders.tsx`, `PnLSurfaceChart.tsx`
- `frontend/src/components/explain/` — `Explainable.tsx`, `ExplainDrawer.tsx`, `ExplainContext.tsx`
- `frontend/src/lib/portfolio/parseCsv.ts`
- `frontend/src/hooks/` — `usePortfolio.ts`, `usePortfolioGreeks.ts`, `useScenarioPnl.ts`

**Modifies (coordinated with WS5 owner — these are the only shared files):** `app/page.tsx` (mount rail + scenario + explain overlays — WS5 lands the shell grid first, WS6 fills the slots); `HedgePanel.tsx` (consume rail's real `portfolio_greeks.delta`; wrap metrics in `<Explainable>`); `OptionsChainTable.tsx` (wrap delta cell in `<Explainable>`).

**New deps:** (optional) `zustand`.

**Acceptance:**
- PortfolioRail: add-position ticket (Zod), CSV paste with per-row badges, virtualized list, aggregate Greeks header. Hedge targets the rail's real delta.
- ScenarioPanel: spot%/IV/DTE sliders (debounced) → `/scenario` → `PnLSurfaceChart` + headline P&L + breakeven + WL-expression strip.
- `<Explainable>` wraps every Wolfram-derived value; one shared `ExplainDrawer` shows inputs → exact WL expression → kernel result → numeric, with green "verified by kernel" (`wolfram`) or amber "numeric fallback (scipy) — NOT Wolfram" (`numeric_fallback`) badge.

**⛓ checkpoint EXPLAIN-LIVE:** with the local kernel running, explain drawer shows `engine:"wolfram"` + reproducible `result_raw`; without the kernel it honestly shows the amber fallback badge.

---

## WS7 — Infra, docker-compose, tests-to-80%  (P3)  🔑
**Depends on:** all (final wiring + coverage gate). File-disjoint from logic workstreams.
**Owns:**
- `backend/Dockerfile`, `docker-compose.yml`, `.env.example`, `frontend/.env.local.example`, `fly.toml`
- `backend/tests/` (pytest, pytest-asyncio, fixtures incl. `fake_wolfram` forcing `numeric_fallback`, `fake_market_provider`, fixture JSON e.g. `SPY_chain.json`)
- `frontend/tests/` (Playwright; fixture-driven visual regression at 320/768/1024/1440)
- CI config (`--cov-fail-under=80`; `alembic upgrade head` + `alembic check` against ephemeral Postgres)

**Acceptance:**
- `docker-compose up` runs backend (alembic→uvicorn) + frontend against hosted `DATABASE_URL`.
- Backend coverage ≥80% with all external systems mocked (Wolfram/yfinance/Groq); a test asserts the forced-fallback path stores `engine_mode:"numeric_fallback"` (never mislabeled).
- Frontend Playwright visual-regression green at the four breakpoints using the fixture.

**⛓ checkpoint FULL-LIVE:** needs the **local Wolfram Engine kernel** (already installed) and `DATABASE_URL`. End-to-end: stream an analysis → values are `wolfram` → persisted `SavedAnalysis` row replayable via `/history/{id}`.

---

## Parallelization summary
- **Wave 1 (after WS0):** WS1, WS3, WS5 run fully in parallel (disjoint dirs: `providers+domain` / `db+core` / `frontend lib+feedback`).
- **Wave 2:** WS2 (needs WS0+WS1), WS6-prep can scaffold against fixtures.
- **Wave 3:** WS4 (needs WS2+WS3), WS6 live (needs WS2+WS5).
- **Wave 4:** WS7 final integration + coverage gate.

## Secret-gating summary
| Resource | Unblocks | Workstreams gated for *live* verification | Status |
|---|---|---|---|
| **Local Wolfram Engine kernel** (`WOLFRAM_KERNEL_PATH`, no secret) | real kernel (`wolfram`) | WS0 (W-KEY), WS2 (API-LIVE), WS6 (EXPLAIN-LIVE), WS7 (FULL-LIVE) | **SATISFIED** — Engine 14.3 installed + activated locally; no cloud keys needed |
| `DATABASE_URL` | hosted Postgres | WS3 (DB-KEY), WS4, WS7 (FULL-LIVE) | pending |
| `GROQ_API_KEY` | live summary node | WS2 summary stage (mocked otherwise) | pending |

W-KEY no longer needs cloud credentials: it is satisfied by the local Wolfram
Engine, which is installed. Until the remaining resources arrive, every
workstream builds and passes its tests against the **labeled numeric fallback**
and mocks — no workstream is blocked from *implementation*, only from *live*
verification at the marked checkpoints.
