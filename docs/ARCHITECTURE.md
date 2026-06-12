# DeltaForge — Production Architecture

> Single source of truth for the system. Every field name in this document is **canonical** and MUST match across the API (Pydantic), the SSE stream, the Postgres schema, and the frontend Zod schemas. Where the five specialist designs disagreed, the reconciliation rules in §1 win.

---

## 1. Reconciliation rules (read first)

These resolve the conflicts between the five design sections. They are binding.

1. **Wire format is `snake_case` end-to-end.** The API returns `snake_case`. The frontend Zod schemas declare `snake_case` keys and `z.infer` the TS types directly — no `camelCase` transform layer. (The frontend section proposed `camelCase`; that is **rejected** to keep one canonical name set. TS naming convention for *local* variables stays camelCase; only the wire/contract types are snake_case.)
2. **The engine discriminator enum has exactly two values, everywhere:**
   `wolfram` | `numeric_fallback`.
   `wolfram` means a real **local Wolfram Engine kernel** ran the computation. The variants `scipy_fallback`, `wolfram_kernel`, `fallback`, `wolfram_cloud` used in individual sections are **aliases that are NOT used**. DB `engine_mode`, API `engine`, frontend `engine`, and the Python `ComputeSource` enum all use `wolfram` / `numeric_fallback`.
3. **The provenance object is named `WolframComputation` on the wire** (one canonical Pydantic model + one Zod schema). The Python *internal* DTO produced by `WolframService` is `WolframEvaluation`; it is mapped to the wire `WolframComputation` at the API boundary. Field mapping is fixed in §4.4.
4. **Greeks object name is `Greeks`** with fields `delta, gamma, theta, vega, rho`. (The `GreekSet` dataclass in the domain layer is an internal alias mapped 1:1 to `Greeks` at the boundary.)
5. **Stage names are canonical:** `market_data`, `greeks`, `iv_surface`, `portfolio`, `hedge`, `scenario`, `summary`. The frontend uses the same strings. (`PipelineStage` enum in Python carries all of them.)
6. **Portfolio position field is `quantity` (signed int)** on the wire and in the DB. The domain layer may internally use `qty` + `Side`, but it serializes to a single signed `quantity`. No `side` field crosses the wire.
7. **Delta target is explicit and surfaced** as `delta_target` (never a silent default of 0).

---

## 2. System diagram

```
                                   ┌──────────────────────────────────────────────┐
                                   │                FRONTEND (Next.js 14)           │
                                   │  app/page.tsx  ── shell: [Rail | Main | Drawers]│
                                   │   ├─ hooks/useAnalysisStream  (SSE assembler)   │
                                   │   ├─ lib/api/{client,sse,schemas(zod)}          │
                                   │   ├─ React Query cache  ['analysis',sym,dte]    │
                                   │   └─ Explainable → ExplainDrawer (WL proof)     │
                                   └───────────────┬───────────────┬────────────────┘
                                  POST /analyze    │ GET /analyze/  │ GET /health/wolfram
                                  POST /scenario    │   stream (SSE) │ /portfolios /alerts ...
                                                    ▼               ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND (FastAPI, Python 3.11, async)                         │
│  main.py (thin: lifespan + middleware + routers)                                          │
│  ├─ core/      settings · cors · ratelimit(slowapi) · logging(request_id)                 │
│  ├─ routers/   analyze · stream · portfolios · scenario · trade_ticket · watchlist ·      │
│  │             alerts · history · engine                                                   │
│  ├─ graph/     LangGraph pipeline  market_data → greeks → portfolio → hedge → scenario     │
│  │                                  → summary   (astream → SSE events)                     │
│  ├─ providers/ MarketDataProvider(Protocol) → YFinanceProvider → CachingProvider          │
│  │             (yfinance off-loop via ThreadPoolExecutor; RetryPolicy; factory)           │
│  ├─ domain/    portfolio · greeks_aggregation · hedging · ingestion(ticket,csv)           │
│  ├─ analytics.py  OFI + pin_risk (extracted, source-agnostic)                             │
│  ├─ services/wolfram/   ★ WolframService ★  session_pool · expressions · fallback ·       │
│  │             cache · dto    (local WolframLanguageSession kernel pool)                   │
│  ├─ db/        SQLAlchemy 2.0 async · repositories · alembic                               │
│  └─ ops/       APScheduler · alert_evaluator                                              │
└───────────┬───────────────────────────┬───────────────────────────┬──────────────────────┘
            │ local kernel (threads)     │ yfinance (threads)        │ asyncpg
            ▼                            ▼                           ▼
   ┌─────────────────┐         ┌──────────────────┐        ┌─────────────────────┐
   │  WOLFRAM ENGINE │         │   yfinance API   │        │  Postgres (hosted,   │
   │  (LOCAL kernel) │         │   (market data)  │        │  DATABASE_URL)       │
   │  D[], NMinimize │         └──────────────────┘        │  8 tables, JSONB     │
   └─────────────────┘                                     └─────────────────────┘
   numeric_fallback (scipy/numpy) is LABELED, never presented as Wolfram.
```

---

## 3. Canonical API contract

Success responses return the bare model (matches current `res.json()` frontend expectation). Errors return `ErrorEnvelope` (§7).

| Phase | Method | Path | Request | Response |
|---|---|---|---|---|
| P0 | GET | `/health` | – | `HealthResponse` |
| P0 | GET | `/health/wolfram` | – | `EngineStatus` |
| P0 | POST | `/analyze` | `AnalyzeRequest` | `AnalyzeResponse` |
| P1 | GET | `/analyze/stream` | query `symbol,dte_max,portfolio_id?` | `text/event-stream` (§6) |
| P1 | POST | `/portfolios` | `PortfolioCreate` | `Portfolio` |
| P1 | GET | `/portfolios` | – | `list[PortfolioSummary]` |
| P1 | GET | `/portfolios/{id}` | – | `Portfolio` |
| P1 | PUT | `/portfolios/{id}` | `PortfolioUpdate` | `Portfolio` |
| P1 | DELETE | `/portfolios/{id}` | – | `204` |
| P1 | POST | `/portfolios/import-csv` | `CsvImportRequest` | `CsvImportResult` |
| P1 | POST | `/portfolios/{id}/analyze` | `AnalyzeOptions` | `AnalyzeResponse` |
| P1 | POST | `/portfolio/greeks` | `GreeksRequest{positions,symbol,dte_max?}` | `PortfolioGreeks` |
| P2 | POST | `/scenario` | `ScenarioRequest` | `ScenarioSurface` |
| P2 | POST | `/trade-ticket` | `TradeTicketRequest` | `TradeTicket` |
| P3 | GET/POST/DELETE | `/watchlist` | `WatchlistItem` | `list[WatchlistItem]` |
| P3 | GET/POST/PATCH/DELETE | `/alerts` | `AlertCreate` | `Alert` |
| P3 | GET | `/history` | query `symbol?,limit,cursor` | `Paginated[AnalysisHistoryItem]` |
| P3 | GET | `/history/{id}` | – | `AnalyzeResponse` |
| P4 | GET | `/engine/status` | – | `EngineStatus` |
| P4 | POST | `/engine/evaluate` | `WLEvalRequest{expression}` | `WolframComputation` |

`/portfolio/greeks` is added (frontend rail needs a debounced aggregate-greeks endpoint distinct from the full pipeline).

---

## 4. Canonical Pydantic models

Models live in `backend/models/` split into focused files (each <800 lines):
`schemas_common.py`, `schemas_greeks.py`, `schemas_wolfram.py`, `schemas_market.py`, `schemas_portfolio.py`, `schemas_hedge.py`, `schemas_scenario.py`, `schemas_analyze.py`, `schemas_requests.py`.

All response models: `model_config = ConfigDict(frozen=True, extra="forbid")`. Request models: `extra="forbid"`.

### 4.1 Common / enums (`schemas_common.py`)

```python
class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"

class WolframEngine(str, Enum):          # the ONE canonical engine discriminator
    WOLFRAM = "wolfram"                   # a real LOCAL Wolfram Engine kernel ran it
    NUMERIC_FALLBACK = "numeric_fallback"

class PipelineStage(str, Enum):
    MARKET_DATA = "market_data"
    GREEKS = "greeks"
    IV_SURFACE = "iv_surface"
    PORTFOLIO = "portfolio"
    HEDGE = "hedge"
    SCENARIO = "scenario"
    SUMMARY = "summary"

class InstrumentType(str, Enum):
    EQUITY = "equity"
    CALL = "call"
    PUT = "put"
```

### 4.2 Greeks (`schemas_greeks.py`)

```python
class Greeks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    delta: float
    gamma: float
    theta: float    # per-day decay (already /365)
    vega: float     # per 1 vol point (per 0.01 IV)
    rho: float = 0.0
```

### 4.3 Wolfram provenance — the differentiator (`schemas_wolfram.py`)

```python
class WolframComputation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    label: str                       # "Portfolio Delta (D[price,S])"
    expression: str                  # EXACT WL string sent/displayed (InputForm)
    engine: WolframEngine            # wolfram | numeric_fallback
    inputs: dict[str, float | str] = {}    # S,K,r,sigma,T,... for explain drawer
    result_raw: str | None = None    # kernel ToString[..,InputForm], None on fallback
    result_numeric: float | None = None
    evaluated: bool                  # True only if a real kernel ran it
    duration_ms: float | None = None
    fallback_reason: str | None = None   # set IFF engine == numeric_fallback
    error: str | None = None
    evaluated_at: datetime
```

### 4.4 `WolframEvaluation` (internal) → `WolframComputation` (wire) mapping

`WolframService` produces the frozen dataclass `WolframEvaluation`; the API maps it:

| `WolframEvaluation` (internal) | `WolframComputation` (wire) |
|---|---|
| `operation` | `label` (humanized) |
| `source` (`ComputeSource`) | `engine` (`WolframEngine`, identical values) |
| `wl_input` | `expression` |
| `wl_output` | `result_raw` |
| `result` (scalar→) | `result_numeric` |
| `succeeded` | `evaluated` |
| `kernel_ms` | `duration_ms` |
| `fallback_reason` | `fallback_reason` |
| `messages`/exception | `error` |

`ComputeSource` (Python enum) values are identical to `WolframEngine`: `wolfram`, `numeric_fallback`.

### 4.5 Market (`schemas_market.py`)

```python
class OptionQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    strike: float
    type: OptionType
    expiry: str                      # YYYY-MM-DD
    bid: float
    ask: float
    last_price: float
    volume: int = Field(ge=0)
    open_interest: int = Field(ge=0)
    iv: float = Field(ge=0.0)        # decimal (0.18 = 18%)
    ofi: float = Field(ge=-1.0, le=1.0)
    greeks: Greeks
    delta: float                     # convenience mirror of greeks.delta
    moneyness: float                 # spot/strike
    wolfram: WolframComputation | None = None

class IVStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    iv_rank: float = Field(ge=0.0, le=100.0)
    iv_percentile: float = Field(ge=0.0, le=100.0)
    atm_iv: float
    iv_30d_high: float
    iv_30d_low: float
    term_structure: list[tuple[str, float]] = []

class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    spot_price: float
    timestamp: datetime
    expiry_used: str
    near_expiry_filter_used: str
    dte: int
    order_flow_imbalance: float = Field(ge=-1.0, le=1.0)
    pin_risk_score: float = Field(ge=0.0, le=1.0)
    max_pain_strike: float
    iv_stats: IVStats
    calls_count: int
    puts_count: int
    chain: list[OptionQuote]
    data_source: str = "yfinance"    # provider .name → provenance
```

### 4.6 Portfolio (`schemas_portfolio.py`)

```python
class PortfolioPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str | None = None
    symbol: str
    instrument: InstrumentType = InstrumentType.CALL
    strike: float | None = None      # required iff option
    expiry: str | None = None        # required iff option
    quantity: int                    # SIGNED; negative = short  (canonical, no `side`)
    avg_price: float | None = None
    greeks: Greeks | None = None     # filled after pricing
    wolfram: WolframComputation | None = None

class PortfolioGreeks(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float = 0.0
    net_delta_dollars: float         # delta × spot × 100 × contracts
    beta_weighted_delta: float | None = None
    per_position: dict[str, Greeks] = {}    # position_id → per-leg greeks
    wolfram: WolframComputation | None = None

class Portfolio(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    name: str
    positions: list[PortfolioPosition]
    created_at: datetime
    updated_at: datetime
```

### 4.7 Hedge (`schemas_hedge.py`)

```python
class HedgeRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: str
    delta_neutral_ratio: float
    contracts_to_trade: int
    option_type_to_trade: OptionType
    strike_to_trade: float
    expiry_to_trade: str
    expected_pnl_range: tuple[float, float]
    current_portfolio_delta: float    # the REAL delta being neutralized
    residual_delta_after_hedge: float
    delta_target: float               # explicit, surfaced (not silent 0)
    wolfram_computation_used: str     # legacy combined WL string (UI still renders)
    wolfram: WolframComputation       # structured NMinimize provenance
    reasoning: str
```

### 4.8 Scenario (`schemas_scenario.py`)

```python
class ScenarioAxis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: Literal["spot_pct", "iv_pct", "dte"]
    values: list[float]

class ScenarioSurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    x_axis: ScenarioAxis             # spot_pct
    y_axis: ScenarioAxis             # iv_pct
    pnl_grid: list[list[float]]      # [y][x] portfolio P&L
    base_pnl: float
    breakeven_spot: float | None = None
    wolfram: WolframComputation      # symbolic P&L surface expr
    is_stub: bool = True             # honest: True in P0 until P2 wires it
```

### 4.9 Engine status (`schemas_wolfram.py`)

```python
class EngineStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    wolfram_available: bool          # real kernel reachable (canary 1+1==2)
    engine_in_use: WolframEngine
    kernel_version: str | None = None
    pool_size: int = 0
    healthy_sessions: int = 0
    last_probe_ms: float | None = None
    reason: str | None = None        # "kernel_unavailable","eval_timeout",...
    note: str
    last_checked: datetime
```

### 4.10 Top-level `/analyze` response (`schemas_analyze.py`) — the whole dashboard

```python
class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    # identity / HUD scalars
    symbol: str
    spot_price: float
    expiry: str
    calls_count: int
    puts_count: int
    order_flow_imbalance: float
    pin_risk_score: float
    iv_rank: float                    # = market.iv_stats.iv_rank (was hardcoded 0)
    # full renderable payloads
    market: MarketSnapshot            # chain + iv_stats
    options_chain: list[OptionQuote]  # mirror of market.chain (UI reads top-level)
    portfolio_greeks: PortfolioGreeks # HUD Delta/Gamma/Theta (was all 0)
    hedge: HedgeRecommendation
    scenario: ScenarioSurface         # stub in P0
    # narrative + provenance
    risk_summary: str
    wolfram_computation_used: str     # legacy top-level string
    wolfram_computations: list[WolframComputation]   # every expr this run
    engine_status: EngineStatus
    analysis_id: str | None = None    # set once persisted (P3)
    generated_at: datetime
    disclaimer: str = "Informational only. Not investment advice. No live execution."
```

### 4.11 Selected request models (`schemas_requests.py`)

```python
class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=8, pattern=r"^[A-Za-z.\-]+$")
    dte_max: int = Field(default=7, ge=1, le=365)
    positions: list[PortfolioPosition] | None = None

class PortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    positions: list[PortfolioPosition] = Field(min_length=1)

class CsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: str = Field(min_length=1, max_length=200_000)
    symbol: str | None = None

class CsvRowError(BaseModel):
    row_number: int
    raw: dict[str, str]
    message: str

class CsvImportResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    positions: list[PortfolioPosition]
    rejected: list[CsvRowError]

class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portfolio_id: str | None = None
    positions: list[PortfolioPosition] | None = None
    spot_pct_range: tuple[float, float, float]   # (lo, hi, step)
    iv_pct_range: tuple[float, float, float]
    dte_override: int | None = None

class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str
    kind: Literal["delta_drift", "pin_risk", "gamma_spike"]
    threshold: float
    tolerance: float | None = None
    dte_window: int | None = None
    portfolio_id: str | None = None
```

---

## 5. WolframService — the headline feature

> Symbolic math doesn't hallucinate — **but only if we prove the kernel ran it.** Every Greek, hedge, and P&L surface ships with the exact WL string evaluated and a flag stating whether the real **local Wolfram Engine kernel** (`wolfram`) or a labeled numeric fallback (`numeric_fallback`) produced it. The numeric fallback is **never** styled as Wolfram.

### 5.1 File layout

```
backend/services/wolfram/
├── __init__.py        # exports WolframService, ComputeSource, DTOs
├── service.py         # WolframService: lifecycle, public methods, try-wolfram-then-fallback
├── session_pool.py    # local kernel pool (ThreadPoolExecutor) + timeouts + retries
├── expressions.py     # pure WL-string builders (ported from legacy agent)
├── fallback.py        # numeric (numpy/scipy/mpmath) — ALWAYS labeled numeric_fallback
├── cache.py           # content-addressed eval cache (LRU; Redis-swappable in P3)
└── dto.py             # frozen DTOs: WolframEvaluation, GreeksResult, HedgeResult, ...
```

**The legacy `backend/agents/wolfram_risk_agent.py` is deleted.** Its fake `import wolfram_client` and `_run_wolfram_mcp` raising `NotImplementedError` are exactly the dishonesty this removes. Its WL-string builders (`fd_expr`, `nm_expr`, combined `wolfram_computation_used`) are **ported** into `expressions.py`.

### 5.2 Kernel, config, pooling

Dependency: `wolframclient>=1.1.0` driving a **local Wolfram Engine 14.3 kernel**
(free developer license, already installed + activated). There is **no Wolfram
Cloud and no Secured Authentication Key** — the kernel binary is a local install,
not a secret. Config loaded once at startup, never hardcoded:

```python
class WolframSettings(BaseSettings):
    wolfram_kernel_path: str | None = None   # WOLFRAM_KERNEL_PATH; default = installed WolframKernel.exe
    wolfram_pool_size: int = 2               # local kernels are heavy processes
    wolfram_eval_timeout_s: float = 20.0
    wolfram_connect_timeout_s: float = 30.0  # kernel launch is slow
    wolfram_max_retries: int = 2
    wolfram_cache_max: int = 2048
    wolfram_enabled: bool = True    # kill-switch → forces numeric_fallback if False
```

- The kernel is started locally via `wolframclient`'s process-based session:
  ```python
  from wolframclient.evaluation import WolframLanguageSession
  session = WolframLanguageSession(settings.resolved_kernel_path())
  session.start(block=True)
  ```
- `WolframLanguageSession` is **synchronous and process-based** (not thread-safe), so each kernel runs on its own dedicated 1-worker `ThreadPoolExecutor`; the async API wraps every call in `loop.run_in_executor` + `asyncio.wait_for` (this is the *only* Wolfram path that uses the executor — unlike the rejected cloud design).
- **Pool**: at lifespan startup, create `wolfram_pool_size` pre-started kernels guarded by a `BoundedSemaphore`. `async with pool.acquire() as kernel:` leases one. A crashed/errored kernel is terminated + discarded + lazily replaced, not returned. If **zero** kernels start, the service flips to `numeric_fallback` mode and logs CRITICAL — it never crashes.
- **Missing/unstartable kernel** (no binary on disk, `wolframclient` absent, or a failed launch) → constructs fine, starts in `numeric_fallback`, `health()` reports `reason="kernel_unavailable"`.
- **Timeouts**: `asyncio.wait_for` around kernel launch (connect) and each `evaluate_wrap` (eval). A timed-out kernel is poisoned (terminated + replaced).
- **Retries**: exp backoff + jitter, **only** for transport/process-transient errors (`TimeoutError`, `OSError`/`BrokenPipeError`, kernel-process exceptions). A `WolframLanguageException` / kernel message is a deterministic math error — **not retried**; returns a failed evaluation and the caller decides whether to fall back.

### 5.3 Public surface (all async, all return frozen DTOs)

```python
class WolframService:
    async def contract_greeks(self, c: GreekInputs) -> GreeksResult: ...
    async def portfolio_greeks(self, positions: Sequence[Position]) -> PortfolioGreeksResult: ...
    async def delta_neutral_hedge(self, req: HedgeRequest) -> HedgeResult: ...
    async def pnl_surface(self, req: ScenarioRequest) -> PnLSurfaceResult: ...
    async def health(self) -> EngineStatus: ...
```

Every method: build expression → `_eval()` → on failure/unavailable call labeled `fallback.py` → assemble a result DTO carrying **both** expression string and result. Orchestration (try-wolfram-then-fallback) lives in the service; builders + fallback math stay pure and independently testable.

### 5.4 The exact WL expressions (in `expressions.py`)

Numeric values are injected via `wlexpr`/`export(target_format="wl")`, never f-string concatenation (the old `f"{spot:.4f}"` is retained **only** as the display string).

- **Per-contract Greeks** — symbolic `D[]` on the closed-form Black–Scholes price (`cp=+1` call, `-1` put), returning a `<|"price"->..,"delta"->D[bs,S],"gamma"->D[bs,{S,2}],"vega"->D[bs,sig],"theta"->-D[bs,T],"rho"->D[bs,r]|>` Association → deserializes to a Python dict. Theta reported per-year, UI divides by 365.
- **Portfolio aggregate Greeks** — the whole `book` matrix injected via `export`; kernel computes `Total[bsGreeks @@@ book]` so the aggregate is itself kernel-verified.
- **Delta-neutral hedge** — `NMinimize[(currentDelta + vars·hedgeDeltas - deltaTarget)^2 + lambda·Total[Abs[vars]], constraints]` with per-leg + gross caps and `Method->"DifferentialEvolution"`. Multi-instrument (`vars·hedgeDeltas` dot product), real target. Replaces the legacy "1 contract on highest-OI strike, target=0" heuristic.
- **Scenario P&L surface** — symbolic `pnl[S,sig,T] = portfolioValue[S,sig,T] - baseValue`, evaluated over a `Table` grid (spot×IV×time); the same `pnl` serves a single-slider eval and the full grid.

### 5.5 Verifiability capture (the anti-hallucination contract)

Every eval produces an immutable `WolframEvaluation` (dto.py):

```python
class ComputeSource(str, Enum):
    WOLFRAM = "wolfram"                 # a real LOCAL Wolfram Engine kernel ran it
    NUMERIC_FALLBACK = "numeric_fallback"

@dataclass(frozen=True)
class WolframEvaluation:
    operation: str
    source: ComputeSource          # the trust anchor
    wl_input: str                  # exact InputForm sent
    wl_output: str | None          # kernel's ToString[result,InputForm], verbatim
    result: Any                    # deserialized python value
    messages: tuple[tuple[str, str], ...]
    kernel_ms: float | None
    succeeded: bool
    cache_hit: bool
    fallback_reason: str | None    # set IFF source == NUMERIC_FALLBACK
```

`wl_output` is obtained by wrapping the payload server-side as `<|"value"->(expr),"form"->ToString[(expr),InputForm]|>` and calling **`evaluate_wrap`** (exposes `.result` + `.messages`; any message ⇒ success False). The customer can paste `wl_output` into Wolfram and reproduce it — that round-trip *is* the proof.

### 5.6 Fallback policy (always labeled)

`fallback.py` mirrors each builder numerically (numpy/scipy closed-form Greeks; `differential_evolution` for the hedge; vectorized numpy P&L grid). Hard rules:
- Always carries `source = NUMERIC_FALLBACK` + non-null `fallback_reason` ∈ `{kernel_unavailable, kernel_unreachable, eval_timeout, wolfram_message_error, kill_switch}`.
- Still emits `wl_input` (the expression we *would* run) but `wl_output = None`.
- **No silent promotion** — a test fails if any fallback path can emit `WOLFRAM_CLOUD`.
- Parity test: both paths on identical inputs agree within tolerance.

### 5.7 Cache (`cache.py`)

Key = `sha256` of canonical InputForm (post-`export`) namespaced by `operation` + `WL_BUILDER_VERSION`. Store = `cachetools.LRU` (size `wolfram_cache_max`), short TTL on market-derived results, ~no TTL on pure-symbolic structure. **Only successful** evals cached (a transient outage can't pin a fallback). Cache hits preserve original `source` + `wl_output`. `CacheBackend` Protocol lets P3 swap to Redis without touching call sites.

### 5.8 Health (`/health/wolfram` → `EngineStatus`)

`health()` runs a **live canary** (`wl.Plus(1,1)` expecting `2`) through a real local kernel with a tight timeout, not just checking that a kernel object exists. Result cached a few seconds. Backs the P4 "symbolic engine status" pill: green only when the canary round-trips and returns verified `2`; amber/red with the real `reason` otherwise. SSE emits the active `ComputeSource` per stage so the user sees live which engine produced each number.

---

## 6. SSE streaming — `GET /analyze/stream`

`StreamingResponse(media_type="text/event-stream")`, GET (query params). Async generator drives the graph via `.astream()`; blocking yfinance runs in the executor; Wolfram runs on-loop. Framing: `event: <name>\nid: <seq>\ndata: <json>\n\n`; heartbeat `: keepalive\n\n` every 15s. Client closes on `done`/`error`. UI reduces by event name (out-of-order safe); `done` is authoritative.

| Order | `event:` | `data:` payload | UI effect |
|---|---|---|---|
| 1 | `stage` | `{stage:"market_data", status:"start"}` | chain skeleton |
| 2 | `market` | `MarketSnapshot` | HUD scalars + chain + IV surface |
| 3 | `stage` | `{stage:"greeks", status:"done"}` | per-row greeks settle |
| 4 | `portfolio` | `PortfolioGreeks` | Δ/Γ/Θ HUD + rail aggregate |
| 5 | `stage` | `{stage:"iv_surface", status:"done"}` | IV surface ready |
| 6 | `stage` | `{stage:"hedge", status:"start"}` | HedgePanel skeleton |
| 7 | `wolfram` | `WolframComputation` (one per expr; repeats) | explain drawer fills live |
| 8 | `hedge` | `HedgeRecommendation` | HedgePanel fills |
| 9 | `scenario` | `ScenarioSurface` | scenario panel (stub/real) |
| 10 | `summary` | `{risk_summary:str}` (opt. token `summary_delta`) | Groq narrative streams |
| 11 | `engine` | `EngineStatus` | status pill resolves honestly |
| 12 | `done` | `AnalyzeResponse` (full canonical) | final reconcile |
| any | `error` | `ErrorEnvelope` | toast + stop spinners |

---

## 7. Error envelope + validation

Single error shape for every non-2xx (matches what `AnalyzeForm` reads — `body.detail`):

```python
class FieldError(BaseModel):
    loc: list[str]; msg: str; type: str

class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    error: str          # "validation_error"|"upstream_data"|"wolfram_eval"|"not_found"|"rate_limited"|"internal"
    detail: str
    stage: PipelineStage | None = None
    field_errors: list[FieldError] | None = None
    request_id: str
    timestamp: datetime
```

- Boundary: all requests `extra="forbid"`; `RequestValidationError` → `ErrorEnvelope{error:"validation_error"}` at 422.
- Domain: typed exceptions `UpstreamDataError`→502, `SymbolNotFound`→404, `NoChainData`→422, `RateLimitError`→429, `NotFoundError`→404. Provider taxonomy in `providers/errors.py` (`ProviderUnavailable`→503).
- **Wolfram honesty**: a kernel failure does **not** 500 — it degrades to `numeric_fallback`, sets `engine_status.engine_in_use = numeric_fallback`, attaches `WolframComputation.error`/`fallback_reason`. The response still succeeds. Only a total compute failure errors out.
- Global handler: unhandled → `error:"internal"`, generic detail (no stack/secret leak), full context logged with `request_id`.

---

## 8. MarketDataProvider + Portfolio domain

### 8.1 Provider abstraction (`backend/providers/`)

`base.py` defines a `runtime_checkable Protocol` + raw frozen-dataclass DTOs (`Quote`, `RawContract`, `RawChain`). The provider returns **raw** data only — never Greeks (Greeks come from `WolframService` for verifiability; provider-supplied Greeks are never trusted).

```python
@runtime_checkable
class MarketDataProvider(Protocol):
    name: str
    async def get_spot(self, symbol: str) -> Quote: ...
    async def get_expirations(self, symbol: str) -> tuple[str, ...]: ...
    async def get_chain(self, symbol: str, expiry: str) -> RawChain: ...
```

- All async (future Tradier/Polygon via `httpx.AsyncClient` slot in unchanged).
- `YFinanceProvider` wraps each blocking call in `run_in_executor` against one shared `ThreadPoolExecutor(max_workers=8)` created at lifespan. The legacy `time.sleep` retry loop is removed; retry moves to async `RetryPolicy` (`asyncio.sleep`, full jitter, only transient exceptions).
- `CachingProvider` decorates any provider; per-method TTL (`get_spot` 5s, `get_chain` 30s, `get_expirations` 1h), keyed `(provider.name, method, symbol, expiry)`, single-flight via per-key `asyncio.Lock`. Cache backend swappable to Redis in P3.
- `factory.build_market_data_provider(settings, executor)` selects by `MARKET_DATA_PROVIDER` env; missing creds fail fast at startup. `provider.name` flows to `MarketSnapshot.data_source`.
- OFI + pin-risk extracted from the legacy agent into source-agnostic `backend/analytics.py`.

### 8.2 Portfolio domain (`backend/domain/`)

Internal frozen value objects (`portfolio.py`): `Position(symbol, instrument, qty>0, side, cost_basis, strike?, expiry?, position_id)` with `signed_qty` derived. **At the API boundary this serializes to the canonical `PortfolioPosition` with a single signed `quantity`** (no `side` on the wire — §1 rule 6). Constants: `EQUITY_MULTIPLIER=1`, `OPTION_MULTIPLIER=100`.

- Per-leg Greeks come from `WolframService` (symbolic `D[]`), returning `Greeks` + the WL expression + honest `engine`. Equity is the degenerate case: delta=1, rest=0, no kernel call.
- `greeks_aggregation.aggregate_portfolio_greeks(positions, leg_greeks)` is a **pure** function: `Σ signed_qty × multiplier × per_unit_greek`. Trivially unit-testable to 80%+. Output feeds `PortfolioGreeks` → HUD cards (kills the all-zero mock path).
- **Real delta target** (`hedging.py`): `net_delta = aggregate(...).delta`; `HEDGE_TARGET_DELTA = 0.0` (configurable); `delta_to_hedge = HEDGE_TARGET_DELTA - net_delta`. Fed to `WolframService.delta_neutral_hedge` (NMinimize). Multi-symbol portfolios hedge **per underlying** (group legs by `symbol`). Empty portfolio ⇒ net_delta 0, explicit "no exposure" state (no fake 1-contract trade).

### 8.3 Ingestion (`backend/domain/ingestion/`)

- `ticket.py` — `PositionTicket` Pydantic model: positive qty, non-negative cost basis, symbol normalized + whitelisted, option ⇒ strike+expiry present and expiry not past, equity ⇒ no strike/expiry. `.to_position()` → frozen `Position`.
- `csv_parser.py` + `aliases.py` — tolerant: `csv.Sniffer` for delimiter (comma/tab/semicolon), header alias map, value coercers (strip `$`/`,`, instrument/side synonyms, multi-format dates → ISO), each row through the **same** `PositionTicket` validator (DRY). Per-row `CsvRowError`; valid rows never discarded for sibling failures. 1,000-row cap (named const). Returns `CsvImportResult{positions, rejected}`.

---

## 9. Postgres schema (P3)

SQLAlchemy 2.0 typed ORM, async `asyncpg`, UUID PKs. **Every table has nullable indexed `user_id`** so auth drops in later via a non-destructive `ALTER` (no rebuild). `saved_analyses` + `alert_events` are append-only audit tables.

### 9.1 Base + mixins (`db/base.py`)

`Base(DeclarativeBase)` with `MetaData(naming_convention=...)` (stable `ix/uq/ck/fk/pk` names → clean reversible migrations). `PKMixin(id: UUID=uuid4)`, `TimestampMixin(created_at, updated_at)`, `TenantMixin(user_id: UUID|None, indexed)`.

### 9.2 Tables (8)

```
portfolios(id, name, base_currency, notes, +tenant +ts)
  1──* positions(portfolio_id FK CASCADE, symbol, instrument_type ∈ {equity,call,put},
                 quantity Numeric(18,4) SIGNED, multiplier int(=100/1), avg_price,
                 strike?, expiry?, implied_vol?, source ∈ {manual,csv}, +tenant +ts)
       CHECK instrument_type valid; CHECK option⇒strike+expiry NOT NULL

saved_analyses (APPEND-ONLY audit + Wolfram reproducibility)
  (portfolio_id? FK SET NULL, symbol, dte_max, spot_price, expiry_used,
   order_flow_imbalance, pin_risk_score,
   engine_mode ∈ {wolfram, numeric_fallback},            ← canonical enum (§1)
   wolfram_inputs JSONB, wolfram_expressions JSONB, wolfram_raw_result JSONB,
   wolfram_computation_used TEXT,
   portfolio_greeks JSONB, hedge_recommendation JSONB, risk_summary TEXT,
   groq_model?, +tenant +ts)
   CHECK engine_mode valid

watchlists 1──* watchlist_items(watchlist_id FK CASCADE, symbol,
                 UNIQUE(watchlist_id,symbol), +tenant +ts)

alerts(portfolio_id? FK CASCADE, symbol, kind ∈ {delta_drift,pin_risk,gamma_spike},
       threshold, tolerance?, dte_window?, is_active, cooldown_seconds,
       last_evaluated_at?, last_triggered_at?, +tenant +ts)
  1──* alert_events (APPEND-ONLY: alert_id FK CASCADE, triggered_at, observed_value,
                 threshold_at_trigger, message, snapshot JSONB,
                 saved_analysis_id? FK SET NULL, +tenant +ts)
```

> **Reconciliation:** the persistence section used `engine_mode ∈ {wolfram_cloud, scipy_fallback}`. Per §1 rule 2 (and the local-kernel contract) this becomes `{wolfram, numeric_fallback}`. The CHECK constraint and the `fake_wolfram` test fixture use `numeric_fallback`.

### 9.3 Repositories (`db/repositories/`)

Generic `AsyncRepository[T]` (`get/list/add/delete`, `flush` not `commit`). Append-only repos (`SavedAnalysisRepository`, alert events) **omit** update/delete. Commit owned by the request `get_session` dependency (unit of work) or the scheduler job. Business logic depends on the `Repository` Protocol, not SQLAlchemy.

### 9.4 Alembic

`alembic init`; `env.py` imports `Base.metadata` + all models; reads `DATABASE_URL`, converts async→sync (`postgresql+psycopg://`) for the runner. Migration 0001 = full schema + `alert_kind` enum. Future auth = one additive migration (`users` table + FKs on existing `user_id`, optional `SET NOT NULL` after backfill). Migrations run as a one-shot compose/release step, **not** in the app process. CI gate: `alembic upgrade head` + `alembic check`.

---

## 10. Frontend redesign (P0–P2)

### 10.1 Kill runtime mock
- Delete type defs from `lib/mock-data.ts`; **`src/lib/api/schemas.ts` (Zod) is the single source of truth**, `types/index.ts` re-exports `z.infer` types. Every component imports from `@/types`.
- Schemas are **snake_case** (§1 rule 1) — no transform layer; TS contract types mirror the wire exactly.
- Mock object → `src/__fixtures__/analysis.fixture.ts` typed as `AnalysisResult`, imported only by `*.stories.tsx`/`*.test.tsx`. ESLint `no-restricted-imports` bans `__fixtures__` from `src/app/**` + `src/components/**`.
- Per-panel 4-state machine (`idle|loading|ready|error`) via `<PanelState>` replaces the `previewMode` boolean. Shape-matched skeletons (CLS < 0.1).

### 10.2 Data layer
- `lib/api/{client,sse,schemas}.ts`: `analyze()` (POST, non-stream, for tests/fallback) + `analyzeStream()` (POST via `fetch` ReadableStream + hand-rolled SSE parser, since `EventSource` is GET-only — but `/analyze/stream` is GET, so `EventSource` is viable; client supports both). Zod `.parse()` on each frame (fail loud).
- React Query: `useAnalysisStream` accumulates stage payloads into one `AnalysisResult` under `['analysis',symbol,dteMax]` via `setQueryData`; exposes `stages: Record<StageName,StageStatus>`. `usePanelStatus(stage)` derives the 4-state.

### 10.3 New shell
`Header(live engine badge) → [PortfolioRail(300px) | MainColumn(minmax(0,1fr))] → ScenarioPanel`, with `ExplainDrawer` + scenario as overlays. Replaces the flat `space-y-4` stack.

- **PortfolioRail (P1)**: aggregate Greeks header (Δ Γ Θ V, net-delta emphasis), virtualized positions list, add-position ticket, CSV-paste import (`lib/portfolio/parseCsv.ts`, tolerant, per-row badges), disclaimer footer. `usePortfolio` (client state) + `usePortfolioGreeks` (debounced POST `/portfolio/greeks`). HedgePanel consumes the rail's real `portfolio_greeks.delta`.
- **ScenarioPanel (P2)**: spot%/IV/DTE sliders (debounced ~200ms) → POST `/scenario` → `PnLSurfaceChart` (Recharts heatmap/line, terminal palette) + headline P&L + breakeven + WL-expression strip. `useScenarioPnl` (SWR-cached grids).
- **Explain drawer (P2, the differentiator)**: `<Explainable computation={...}>` wraps every Wolfram-derived value (dotted underline + `ƒ` glyph); click opens one shared `ExplainDrawer` (via `ExplainContext`) showing inputs → exact WL expression (copyable) → kernel result → numeric, with a **green "verified by kernel"** badge when `engine === "wolfram"` or an **amber "numeric fallback (scipy) — NOT Wolfram"** badge when `engine === "numeric_fallback"`.
- **Symbolic engine badge (P4-ish, lands P1)**: `SymbolicEngineBadge` polls `/health/wolfram` (`useWolframHealth`, 30s) → green "WOLFRAM KERNEL · LIVE"+latency / amber "NUMERIC FALLBACK" / gray "CHECKING…". Replaces the static `WOLFRAM MCP / READY` lie in `Header.tsx`.
- **Chain virtualization**: `OptionsChainTable` → `@tanstack/react-virtual`, ATM-anchored scroll + sticky ATM divider, per-row delta column (each cell `<Explainable>`), memoized `useChainRows` selector.

### 10.4 Frontend types (Zod-inferred, snake_case)
`WolframComputation, Greeks, OptionQuote, PortfolioPosition, PortfolioGreeks, HedgeRecommendation, MarketSnapshot, IVStats, ScenarioSurface, EngineStatus, AnalyzeResponse` — **identical field names to §4**. `engine: "wolfram" | "numeric_fallback"`. `StageName = "market_data"|"greeks"|"iv_surface"|"portfolio"|"hedge"|"scenario"|"summary"`. `StageStatus = "idle"|"loading"|"ready"|"error"`.

### 10.5 Aesthetic
Keep `#0a0b0d` bg, `#0052ff` accent, `cb-card` glass, font-mono, orbs/grain. Promote hardcoded colors to CSS vars (`--df-text-muted, --df-up, --df-down, --df-warn`). **Delete** orphan `RiskDashboard.tsx` + `HedgeCard.tsx` (unused `df-*`/`#00d4ff` system) after confirming no imports. New deps: `@tanstack/react-query`, `@tanstack/react-virtual`, `zod`, (optional) `zustand`.

---

## 11. Infra / docker-compose

### 11.1 Backend Dockerfile (multi-stage)
`python:3.11-slim` builder (`build-essential` only for scipy/asyncpg wheels) → slim runtime, non-root `app` user, `uvicorn main:app`. `wolframclient` is pure-Python, but it now drives a **local Wolfram Engine kernel** (`WolframKernel.exe` / the platform binary), which must be present on the host running the backend; where the kernel is absent the service degrades to the labeled `numeric_fallback`. Migrations run as a **separate** release/compose step, not in this CMD. Fly/Render-ready: `[deploy] release_command = "alembic upgrade head"`.

### 11.2 docker-compose.yml (local)
```yaml
services:
  backend:
    build: { context: ., dockerfile: backend/Dockerfile }
    env_file: [.env]            # DATABASE_URL → hosted Postgres
    ports: ["8000:8000"]
    command: sh -c "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
    volumes: ["./backend:/app"]
  frontend:
    build: { context: ./frontend }
    env_file: [./frontend/.env.local]   # NEXT_PUBLIC_API_URL=http://localhost:8000
    ports: ["3000:3000"]
    depends_on: [backend]
```
Postgres is **hosted** (locked decision #4), referenced by `DATABASE_URL` — not a compose service (a commented-out `postgres:16` block exists for offline dev only). Cloud: backend → Fly/Render (same Dockerfile, secrets via platform store), frontend → Vercel, CORS allowlist updated with the Vercel domain.

### 11.3 Settings / security (P3)
`core/settings.py` (pydantic-settings): required secrets `GROQ_API_KEY, DATABASE_URL` have **no defaults** → fail-fast at boot. The Wolfram engine needs **no secret** — only the optional `WOLFRAM_KERNEL_PATH` (defaults to the installed `WolframKernel.exe`); a missing/unstartable kernel degrades to `numeric_fallback`, it never fails boot. `.env` git-ignored; `.env.example` documents placeholders. CORS: replace `allow_origins=["*"]` with env `CORS_ALLOW_ORIGINS` (the `*` + `allow_credentials=True` combo is invalid/unsafe — locking the list fixes it). Rate limiting via slowapi (`/analyze` tighter, SSE looser). Background alerts via APScheduler `AsyncIOScheduler` (`max_instances=1, coalesce=True, jitter`), `evaluate_all_alerts` groups by symbol (no N+1), respects `cooldown_seconds`, links each firing to a real `saved_analyses` row, records the honest `engine_mode`.

---

## 12. Compliance / disclaimer

Informational only. No live execution — trade tickets are **export/paper only** (`POST /trade-ticket` returns a blob, never routes an order). Every `AnalyzeResponse` carries `disclaimer: "Informational only. Not investment advice. No live execution."`; the frontend renders it in the PortfolioRail footer and the trade-ticket export. Single-tenant now; `user_id` reserved on every table for a future auth layer.
