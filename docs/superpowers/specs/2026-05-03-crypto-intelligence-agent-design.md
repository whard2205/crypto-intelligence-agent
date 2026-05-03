# Crypto Market Intelligence Multi-Agent System — Design Spec

**Date:** 2026-05-03  
**Status:** Approved with Required Revisions  
**Target:** Recruiter-ready MVP demonstrating multi-agent AI engineering for AI/LLM and crypto/fintech roles

---

## 1. Goal

Build a Crypto Market Intelligence Multi-Agent System that collects market, news, social, and on-chain signals for BTC and ETH, analyzes them in parallel, fuses the results through a Claude-powered supervisor, and publishes a concise intelligence report to Telegram on-demand and on a 4-hour schedule, with the same report accessible as structured JSON via FastAPI.

---

## 2. Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Agent orchestration | LangGraph (StateGraph, Send API, reducers) |
| LLM reasoning | Anthropic Claude SDK — Sonnet for supervisor only, Haiku for sentiment and risk |
| API layer | FastAPI + Uvicorn |
| Storage | SQLite (report history, upgradeable to PostgreSQL) |
| Scheduling | APScheduler (AsyncIOScheduler) |
| Telegram | python-telegram-bot v20 (async) |
| HTTP client | httpx (async) |
| Settings | pydantic-settings (`from pydantic_settings import BaseSettings`) |
| Testing | pytest + pytest-asyncio + respx (HTTP mocking) |
| Packaging | pyproject.toml (uv or pip) |
| Container | Dockerfile (single-stage, Python 3.11-slim) |

### pyproject.toml dependencies

```toml
[project]
dependencies = [
    "langgraph>=0.2",
    "anthropic>=0.40",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "python-telegram-bot>=20.0",
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "apscheduler>=3.10",
    "aiosqlite>=0.20",
    "feedparser>=6.0",
    "praw>=7.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]
```

---

## 3. Data Sources

### Free-tier-first strategy

All sources use a `FallbackAdapter` chain: primary → fallback → mock. The system runs fully offline in mock mode for development and CI.

| Domain | Primary | Fallback | Mock |
|---|---|---|---|
| Price / OHLCV | Binance public REST API | CoinGecko free/demo API | `MockPriceAdapter` |
| News | RSS feeds (CoinDesk, CoinTelegraph, Decrypt) | CryptoPanic free tier | `MockNewsAdapter` |
| On-chain (BTC) | Blockchain.com public API | — | `MockOnChainAdapter` |
| On-chain (ETH) | Etherscan free API (API key required) | — | `MockOnChainAdapter` |
| Social sentiment | Reddit via PRAW (`r/CryptoCurrency`, `r/Bitcoin`, `r/ethereum`) | — | `MockSocialAdapter` |

**Initial symbols:** `BTCUSDT`, `ETHUSDT`  
**Later milestone:** `SOLUSDT`

---

## 4. Environment & Cost-Control Settings

All settings loaded via `pydantic-settings` from `.env` or environment variables.

```python
# config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):
    # Environment
    ENV: Literal["development", "test", "production"] = "development"
    MOCK_MODE: bool = False           # force all adapters to mock regardless of ENV

    # LLM
    ANTHROPIC_API_KEY: str
    ANTHROPIC_SUPERVISOR_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_ANALYZER_MODEL: str = "claude-haiku-4-5-20251001"
    LLM_ENABLED: bool = True

    # LLM cost-control (IDR budget)
    DAILY_LLM_BUDGET_IDR: float = 50_000.0    # ~$3 USD
    MAX_LLM_CALLS_PER_DAY: int = 100

    # Data sources
    ETHERSCAN_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "crypto-intel-agent/0.1"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # API
    API_AUTH_ENABLED: bool = False
    API_KEY: str = ""

    # Timezone
    DISPLAY_TIMEZONE: str = "Asia/Jakarta"    # for Telegram formatting

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Mock mode rules

| ENV | MOCK_MODE | Behavior |
|---|---|---|
| `development` | any | Real adapters attempted; mock used as final fallback |
| `test` | any | All adapters forced to mock regardless of MOCK_MODE flag |
| `production` | `false` (default) | Real adapters only; mock **never** used. Source unavailable on failure. |
| `production` | `true` | Explicitly allowed mock (e.g. demo/recruiter run without real keys) |

In `production` with `MOCK_MODE=false`: if all real adapters for price fail → return `ErrorReport`. For non-price sources → mark as unavailable, continue.

### LLM budget enforcement

A `LLMBudgetTracker` (in `services/llm_budget.py`) tracks daily call count and estimated cost. Before each Claude call:
1. If `LLM_ENABLED=false` → skip, use deterministic fallback
2. If daily calls ≥ `MAX_LLM_CALLS_PER_DAY` or estimated cost ≥ `DAILY_LLM_BUDGET_IDR` → skip, use deterministic fallback, append `"llm_budget_exceeded"` to `state["errors"]`
3. Deterministic fallback for analyzers: returns rule-based output (RSI thresholds, keyword scoring) instead of Claude response

---

## 5. Graph Flow

```
START
  │
  ▼
[fan_out_collectors]          ← Send() dispatches all 4 collectors in parallel
  ├── collect_price
  ├── collect_news
  ├── collect_onchain
  └── collect_social
  │
  ▼ (all collectors joined)
[aggregate_raw]               ← normalizes raw fields → NormalizedMarketContext
  │                              deduplicates data_gaps
  │                              CRITICAL CHECK: if price_data is None → route to error_exit
  ▼
[fan_out_analyzers]           ← Send() dispatches all 3 analyzers in parallel
  ├── analyze_sentiment         writes → sentiment_analysis
  ├── analyze_price_pattern     writes → price_pattern_analysis
  └── analyze_risk              writes → risk_analysis
  │
  ▼ (all analyzers joined)
[merge_analysis]              ← combines 3 separate fields → AnalysisResult
  │
  ▼
[supervisor]                  ← Claude Sonnet: fuses context + analysis → IntelligenceReport
  │
  ▼
END                           ← caller (FastAPI route or Telegram handler) reads state["report"]
```

### Critical failure edge

`aggregate_raw` includes a conditional edge: if `price_data` is `None` after all fallbacks including mock (i.e., `MockPriceAdapter` also failed), the graph routes to `error_exit` which sets `state["report"]` to a structured error report and terminates. Price data is the minimum viable signal — a report without it is not meaningful.

### Publishing (outside the graph)

The graph terminates at `supervisor` and returns `state["report"]`. Callers handle publishing:

```
FastAPI route:    result = await graph.ainvoke(state) → return result["report"] as JSON
Telegram handler: result = await graph.ainvoke(state) → await TelegramPublisher.publish(result["report"])
Scheduler job:    result = await graph.ainvoke(state) → await TelegramPublisher.publish(result["report"])
```

This keeps the graph a pure intelligence pipeline, reusable by any publisher.

---

## 6. State Schema

```python
# graph/state.py
from typing import Annotated, Optional, Literal
from typing_extensions import TypedDict
import operator


class NormalizedMarketContext(TypedDict):
    """Output of aggregate_raw. Supervisor and analyzers never see raw API responses."""
    symbol:           str
    price_summary:    dict        # {price, change_24h_pct, volume_24h, high_24h, low_24h, ohlcv_24h}
    news_items:       list[dict]  # [{headline, source, published_at, url}]
    onchain_summary:  dict        # {network, metric: value, ...}
    social_summary:   dict        # {mention_volume, sentiment_hint, sample_posts}
    data_gaps:        list[str]   # deduplicated list of unavailable sources


class AnalysisResult(TypedDict):
    """Output of merge_analysis. Combines all three analyzer outputs."""
    sentiment_score:    Optional[float]      # -1.0 to 1.0
    sentiment_label:    Optional[str]        # "bullish" | "bearish" | "neutral"
    sentiment_drivers:  Optional[list[str]]  # top 3 news/social signals
    price_pattern:      Optional[dict]       # {rsi, ma_trend, momentum, volume_trend}
    risk_level:         Optional[str]        # "low" | "medium" | "high"
    risk_factors:       Optional[list[str]]  # ["BTC whale outflow detected", ...]


class IntelligenceReport(TypedDict):
    run_id:           str
    symbol:           str
    requested_at:     str                    # UTC ISO — pipeline trigger time
    generated_at:     str                    # UTC ISO — supervisor completion time
    market_bias:      Literal["bullish", "bearish", "neutral"]
    confidence_score: float                  # 0.0–1.0
    key_signals:      list[str]              # 3–5 bullet points
    risk_warnings:    list[str]
    narrative:        str                    # 2–3 sentence market summary
    data_gaps:        list[str]              # deduplicated warnings for missing sources

class ErrorReport(TypedDict):
    """Returned when a critical failure prevents report generation (e.g. price unavailable)."""
    run_id:       str
    symbol:       str
    requested_at: str                        # UTC ISO
    generated_at: str                        # UTC ISO
    error:        str


class AgentState(TypedDict):
    # Request metadata
    run_id:        str
    symbol:        str
    requested_at:  str

    # Raw collector outputs — separate fields, reducer-safe for parallel execution
    price_data:    Optional[dict]
    news_data:     Annotated[list, operator.add]   # list append is safe in parallel
    onchain_data:  Optional[dict]
    social_data:   Optional[dict]

    # Post-aggregation: set by aggregate_raw
    context:       Optional[NormalizedMarketContext]

    # Separate analyzer outputs — written independently, merged by merge_analysis
    sentiment_analysis:     Optional[dict]
    price_pattern_analysis: Optional[dict]
    risk_analysis:          Optional[dict]

    # Merged analysis: set by merge_analysis
    analysis:      Optional[AnalysisResult]

    # Final output — IntelligenceReport on success, ErrorReport on critical failure
    report:        Optional[Union[IntelligenceReport, ErrorReport]]

    # Error tracking — reducer-safe for parallel execution
    data_gaps:     Annotated[list[str], operator.add]
    errors:        Annotated[list[str], operator.add]
```

---

## 7. Node Responsibilities

### Collector nodes (run in parallel)

| Node | Adapter chain | Writes to | On total failure |
|---|---|---|---|
| `collect_price` | `BinanceAdapter → CoinGeckoAdapter → MockPriceAdapter` | `price_data` | appends `"price_unavailable"` to `data_gaps` |
| `collect_news` | `RSSFeedAdapter → CryptoPanicAdapter → MockNewsAdapter` | `news_data` (append) | appends `"news_unavailable"` to `data_gaps` |
| `collect_onchain` | `BlockchainComAdapter / EtherscanAdapter → MockOnChainAdapter` | `onchain_data` | appends `"onchain_unavailable"` to `data_gaps` |
| `collect_social` | `RedditAdapter → MockSocialAdapter` | `social_data` | appends `"social_unavailable"` to `data_gaps` |

### `aggregate_raw`

- Reads `price_data`, `news_data`, `onchain_data`, `social_data`
- Normalizes each into a clean schema for downstream consumers
- Builds `NormalizedMarketContext` and sets `state["context"]`
- Deduplicates `state["data_gaps"]` (a reducer may have appended duplicates)
- **Critical check:** if `price_data is None` → sets `state["report"]` to an error report and triggers `error_exit` edge

### Analyzer nodes (run in parallel after `aggregate_raw`)

| Node | Implementation | Input from `context` | Writes to |
|---|---|---|---|
| `analyze_sentiment` | Claude Haiku | `news_items`, `social_summary` | `sentiment_analysis` |
| `analyze_price_pattern` | Pure Python (no LLM) | `price_summary.ohlcv_24h` | `price_pattern_analysis` |
| `analyze_risk` | Claude Haiku | `onchain_summary`, `price_summary` | `risk_analysis` |

`analyze_price_pattern` computes: RSI (14-period), simple MA trend (above/below 20-period MA), volume trend (rising/falling), price momentum (rate of change).

### `merge_analysis`

Reads `sentiment_analysis`, `price_pattern_analysis`, `risk_analysis` — all `Optional[dict]`. Combines into `AnalysisResult` and sets `state["analysis"]`. Handles missing inputs gracefully: fields stay `None` if source analyzer had no data.

### `supervisor`

- Receives `state["context"]` and `state["analysis"]` — never raw API responses
- Single Claude Sonnet call with structured prompt
- Outputs `IntelligenceReport`:
  - `market_bias`: bullish / bearish / neutral
  - `confidence_score`: 0.0–1.0 (lower when data_gaps present)
  - `key_signals`: 3–5 evidence-backed bullets
  - `risk_warnings`: any flags from risk analysis or data gaps
  - `narrative`: 2–3 sentence market intelligence summary
  - `data_gaps`: carried from context (deduplicated)

---

## 8. Data Source Adapter Design

```python
# data_sources/base.py
from abc import ABC, abstractmethod
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


class DataSourceAdapter(ABC):

    @abstractmethod
    async def fetch(self, symbol: str) -> Optional[Any]: ...

    @property
    @abstractmethod
    def source_name(self) -> str: ...


class FallbackAdapter(DataSourceAdapter):
    """Chains adapters in order. Returns first non-None result. Logs each failure."""

    def __init__(self, *adapters: DataSourceAdapter):
        self._chain = adapters

    async def fetch(self, symbol: str) -> Optional[Any]:
        for adapter in self._chain:
            try:
                result = await adapter.fetch(symbol)
                if result is not None:
                    return result
                logger.warning("[%s] returned None for %s", adapter.source_name, symbol)
            except Exception as exc:
                logger.warning("[%s] failed for %s: %s", adapter.source_name, symbol, exc)
        logger.error("All adapters exhausted for symbol %s", symbol)
        return None

    @property
    def source_name(self) -> str:
        names = ", ".join(a.source_name for a in self._chain)
        return f"fallback({names})"
```

Each collector node wires its chain at startup (via dependency injection through `config/settings.py`):

```python
price_adapter   = FallbackAdapter(BinanceAdapter(), CoinGeckoAdapter(), MockPriceAdapter())
news_adapter    = FallbackAdapter(RSSFeedAdapter(), CryptoPanicAdapter(), MockNewsAdapter())
onchain_adapter = FallbackAdapter(BlockchainComAdapter(), MockOnChainAdapter())   # BTC
social_adapter  = FallbackAdapter(RedditAdapter(), MockSocialAdapter())
```

### Rate limiting and caching

Every adapter is wrapped by:
- `RetryDecorator`: async exponential backoff, max 3 attempts, on `httpx.HTTPStatusError` (429, 5xx)
- `TTLCache`: in-memory cache keyed by `(source_name, symbol)`, TTL configurable per source (default: 5 minutes for price, 15 minutes for news/social/on-chain)

---

## 9. Fallback Strategy

1. `FallbackAdapter` tries each adapter — logs failures, returns first success
2. If all adapters return `None`, collector writes `None` to its state field and appends `"<domain>_unavailable"` to `data_gaps`
3. `aggregate_raw` deduplicates `data_gaps` and builds partial `NormalizedMarketContext`
4. **Critical failure:** if `price_data is None` after full chain including mock → graph routes to `error_exit`, report contains `error: "Price data unavailable — cannot generate intelligence report"`
5. All other gaps are non-critical: analysis nodes skip gracefully if their input is `None`
6. Supervisor includes deduplicated `data_gaps` in report: `"⚠️ Social data unavailable — sentiment analysis limited to news only"`
7. Confidence score is reduced proportionally when data gaps are present

---

## 10. Folder Structure

```
crypto-intelligence-agent/
├── agents/
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── price_collector.py       # collect_price node fn
│   │   ├── news_collector.py        # collect_news node fn
│   │   ├── onchain_collector.py     # collect_onchain node fn
│   │   └── social_collector.py      # collect_social node fn
│   ├── analyzers/
│   │   ├── __init__.py
│   │   ├── sentiment_analyzer.py    # analyze_sentiment node fn (Claude Haiku)
│   │   ├── price_pattern_analyzer.py # analyze_price_pattern node fn (pure Python)
│   │   └── risk_analyzer.py         # analyze_risk node fn (Claude Haiku)
│   └── supervisor.py                # supervisor node fn (Claude Sonnet)
├── graph/
│   ├── __init__.py
│   ├── state.py                     # AgentState + all TypedDicts
│   ├── aggregator.py                # aggregate_raw node fn + merge_analysis node fn
│   ├── edges.py                     # conditional edges, critical_failure check
│   └── pipeline.py                  # StateGraph build, compile → exported `graph`
├── data_sources/
│   ├── __init__.py
│   ├── base.py                      # DataSourceAdapter ABC + FallbackAdapter
│   ├── price/
│   │   ├── __init__.py
│   │   ├── binance.py
│   │   └── coingecko.py
│   ├── news/
│   │   ├── __init__.py
│   │   ├── rss_feed.py
│   │   └── cryptopanic.py
│   ├── onchain/
│   │   ├── __init__.py
│   │   ├── blockchain_com.py        # BTC: hash rate, mempool, tx count
│   │   └── etherscan.py             # ETH: gas price, tx volume
│   ├── social/
│   │   ├── __init__.py
│   │   └── reddit.py
│   └── mock/
│       ├── __init__.py
│       ├── mock_price.py
│       ├── mock_news.py
│       ├── mock_onchain.py
│       └── mock_social.py
├── services/
│   ├── __init__.py
│   ├── cache.py                     # TTLCache — in-memory, swappable to Redis
│   ├── rate_limiter.py              # Token bucket async rate limiter
│   └── retry.py                     # async exponential backoff decorator
├── publishers/
│   ├── __init__.py
│   ├── base.py                      # ReportPublisher ABC
│   └── telegram_publisher.py        # formats IntelligenceReport → Telegram Markdown
├── api/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app, lifespan (scheduler start/stop)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── report.py                # GET /report?symbol=BTCUSDT
│   │   └── health.py                # GET /health
│   └── schemas.py                   # Pydantic request/response models
├── scheduler/
│   ├── __init__.py
│   └── jobs.py                      # APScheduler: every 4h → graph.ainvoke → telegram
├── config/
│   ├── __init__.py
│   ├── settings.py                  # Pydantic BaseSettings, .env loading, adapter wiring
│   └── prompts.py                   # All Claude prompt templates (supervisor, sentiment, risk)
├── tests/
│   ├── unit/
│   │   ├── test_adapters.py         # each adapter with mocked HTTP (respx)
│   │   ├── test_analyzers.py        # mocked Claude responses
│   │   └── test_aggregator.py       # aggregate_raw + merge_analysis logic
│   ├── integration/
│   │   ├── test_pipeline.py         # full graph with all mock adapters
│   │   └── test_api.py              # FastAPI TestClient
│   └── fixtures/
│       └── mock_responses.py        # reusable raw API response fixtures
├── docs/
│   └── superpowers/specs/
│       └── 2026-05-03-crypto-intelligence-agent-design.md
├── .env.example
├── pyproject.toml
└── Dockerfile
```

---

## 11. API Contract

### Response schemas

Two distinct Pydantic models — no shared `error` field on `IntelligenceReport`:

```python
# api/schemas.py
from pydantic import BaseModel
from typing import Literal, Optional, Union
from datetime import datetime

class IntelligenceReportResponse(BaseModel):
    run_id:           str
    symbol:           str
    requested_at:     datetime
    generated_at:     datetime
    market_bias:      Literal["bullish", "bearish", "neutral"]
    confidence_score: float
    key_signals:      list[str]
    risk_warnings:    list[str]
    narrative:        str
    data_gaps:        list[str]

class ErrorReportResponse(BaseModel):
    run_id:       str
    symbol:       str
    requested_at: datetime
    generated_at: datetime
    error:        str

ReportResponse = Union[IntelligenceReportResponse, ErrorReportResponse]
```

### `GET /report?symbol=BTCUSDT`

If `API_AUTH_ENABLED=true`, requires header `X-API-Key: <value>`. Missing or invalid key returns `401`.

Response `200 OK`:
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTCUSDT",
  "requested_at": "2026-05-03T10:00:00Z",
  "generated_at": "2026-05-03T10:00:08Z",
  "market_bias": "bullish",
  "confidence_score": 0.74,
  "key_signals": [
    "BTC price up 3.2% in 24h with above-average volume",
    "Mempool activity elevated — network usage rising",
    "News sentiment: 4 bullish articles, 1 neutral"
  ],
  "risk_warnings": ["RSI approaching overbought (68)"],
  "narrative": "Bitcoin shows early accumulation signals with rising on-chain activity and positive news flow. Volume confirms the move but RSI is approaching overbought territory — watch for short-term pullback.",
  "data_gaps": ["social_unavailable"]
}
```

Response `503` (critical failure — price unavailable):
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTCUSDT",
  "requested_at": "2026-05-03T10:00:00Z",
  "generated_at": "2026-05-03T10:00:01Z",
  "error": "Price data unavailable — cannot generate intelligence report"
}
```

Response `401` (API auth enabled, missing/invalid key):
```json
{"detail": "Invalid or missing X-API-Key"}
```

### `GET /health`
```json
{"status": "ok", "version": "0.1.0"}
```

---

## 12. Cross-Cutting Concerns

### Reddit credentials

PRAW requires `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT`. If any are empty:
- `ENV=production`, `MOCK_MODE=false` → `RedditAdapter.fetch()` returns `None` immediately, `"social_unavailable"` appended to `data_gaps`
- `ENV=development/test` or `MOCK_MODE=true` → `MockSocialAdapter` is used as fallback

No exception is raised — missing Reddit credentials are a graceful degradation, not a startup failure.

### Claude output validation

All Claude calls (sentiment, risk, supervisor) return structured JSON. Validation uses a dedicated Pydantic model per call:

```python
# Validation flow for every LLM call
try:
    raw = await claude_client.call(prompt)
    result = OutputModel.model_validate_json(raw)
    return result
except ValidationError:
    repair_raw = await claude_client.call(repair_prompt(raw))
    try:
        return OutputModel.model_validate_json(repair_raw)
    except ValidationError:
        state["errors"].append("llm_validation_failed:<node_name>")
        return deterministic_fallback()
```

Deterministic fallbacks per node:
- `analyze_sentiment` fallback: `{sentiment_score: 0.0, sentiment_label: "neutral", sentiment_drivers: []}`
- `analyze_risk` fallback: `{risk_level: "medium", risk_factors: ["insufficient data for risk assessment"]}`
- `supervisor` fallback: returns a minimal `IntelligenceReport` with `confidence_score: 0.1`, `market_bias: "neutral"`, `narrative: "Analysis unavailable — LLM validation failed"`

### Timezone strategy

- All timestamps stored and passed through the pipeline in **UTC ISO 8601** format (`2026-05-03T10:00:00Z`)
- Telegram display converts to `DISPLAY_TIMEZONE` (default: `Asia/Jakarta`, UTC+7) using `zoneinfo`
- FastAPI responses always return UTC timestamps
- `pyproject.toml` dependency: `zoneinfo` is stdlib in Python 3.9+; no extra package needed

---

## 13. Telegram Report Format

```
📊 *BTC Market Intelligence*
🕐 2026-05-03 17:00 WIB

*Bias:* 🟢 Bullish  |  *Confidence:* 74%

*Key Signals*
• BTC price up 3.2% in 24h with above-average volume
• Mempool activity elevated — network usage rising
• News sentiment: 4 bullish articles, 1 neutral

*Risk Warnings*
⚠️ RSI approaching overbought (68)

*Narrative*
Bitcoin shows early accumulation signals with rising on-chain activity and positive news flow. Volume confirms the move but RSI is approaching overbought territory — watch for short-term pullback.

⚠️ _Social data unavailable — sentiment based on news only_
```

Commands:
- `/report` — triggers two sequential graph runs (BTCUSDT then ETHUSDT), sends one message per symbol
- `/report BTCUSDT` — single symbol graph run
- `/help` — lists commands

---

## 14. MVP Milestones

### Milestone 1 — Data Foundation (Days 1–5)
- `pydantic-settings` `Settings` class with all env vars + mock mode rules
- `DataSourceAdapter` ABC + `FallbackAdapter` with failure logging
- All adapters: Binance, CoinGecko, RSS, CryptoPanic, Blockchain.com, Etherscan, Reddit
- Reddit graceful skip when credentials missing
- All mock adapters for offline dev and CI
- `RetryDecorator` + `TTLCache` + `RateLimiter` + `LLMBudgetTracker`
- Unit tests for all adapters with `respx` HTTP mocking

### Milestone 2 — LangGraph Pipeline (Days 6–10)
- `AgentState` and all TypedDicts in `graph/state.py`
- All 4 collector nodes with fan-out, fallback wiring, and mock mode enforcement
- `aggregate_raw` with normalization, deduplication, and critical failure edge
- All 3 analysis nodes (Haiku for sentiment/risk, pure Python for price pattern)
- Claude output Pydantic validation + repair prompt + deterministic fallback per node
- `merge_analysis` node
- `StateGraph` compilation in `pipeline.py`
- Integration test: full graph with mock adapters, assert `IntelligenceReport` shape

### Milestone 3 — Supervisor + Publishing (Days 11–15)
- `supervisor` node with Claude Sonnet + Pydantic output validation
- Prompt templates in `config/prompts.py`
- `FastAPI` app with `GET /report` and `GET /health`
- `IntelligenceReportResponse` + `ErrorReportResponse` union schema
- Optional `X-API-Key` auth middleware (`API_AUTH_ENABLED` setting)
- `TelegramPublisher` with Markdown formatter + `DISPLAY_TIMEZONE` conversion
- Telegram `/report` command handler
- SQLite report history (store last 100 reports per symbol, older rows pruned on insert)

### Milestone 4 — Scheduler + Polish (Days 16–20)
- `APScheduler` 4-hour job wired through FastAPI lifespan
- `.env.example` with all required keys and inline documentation
- `Dockerfile` (Python 3.11-slim, non-root user)
- `README.md` with architecture diagram, setup guide, demo screenshots, and cost-control notes
- End-to-end smoke test against real APIs (single run, rate-limited)

---

## 15. Testing Plan

| Test type | Scope | Tool |
|---|---|---|
| Unit — adapters | Each adapter in isolation, success + failure + fallback paths | pytest + respx |
| Unit — analyzers | Each analyzer with mocked Claude responses (deterministic) | pytest + unittest.mock |
| Unit — aggregator | `aggregate_raw` normalization, deduplication, critical failure routing | pytest |
| Unit — merge_analysis | Partial input combinations (all None, some None, all present) | pytest |
| Integration — pipeline | Full graph with all mock adapters, assert `IntelligenceReport` structure | pytest-asyncio |
| Fallback test | Disable primary adapter, assert fallback activates, `data_gaps` populated | pytest |
| Critical failure test | All adapters return None for price, assert error report returned | pytest |
| Mock mode test | ENV=production MOCK_MODE=false — assert mock adapters never called | pytest |
| LLM budget test | Exhaust MAX_LLM_CALLS_PER_DAY, assert deterministic fallback returned | pytest |
| LLM validation test | Claude returns malformed JSON, assert repair attempted then fallback | pytest |
| Reddit missing creds test | Empty REDDIT_CLIENT_ID, assert social_unavailable in data_gaps, no exception | pytest |
| API auth test | API_AUTH_ENABLED=true, missing key → 401; valid key → 200 | FastAPI TestClient |
| Timezone test | generated_at stored as UTC, Telegram display shows WIB offset | pytest |
| API test | All endpoints with valid + invalid inputs | FastAPI TestClient |
| E2E smoke | Real APIs, single run, assert report generates, no assertion on content | pytest-asyncio |
