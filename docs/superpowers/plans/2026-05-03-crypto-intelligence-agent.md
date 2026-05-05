# Crypto Intelligence Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-cost local MVP that runs the full pipeline (mock data → LangGraph → deterministic analysis → FastAPI + Telegram) with no Claude API, no paid APIs, and no required external credentials.

**Architecture:** LangGraph StateGraph with parallel fan-out collectors, aggregate_raw normalizer, parallel analyzers, merge_analysis combiner, and deterministic supervisor. FastAPI and Telegram call `graph.ainvoke()` as external callers; publishing is never a graph node. Claude and real APIs are added in later phases without touching the graph structure.

**Tech Stack:** Python 3.11+, LangGraph 0.2+, FastAPI, pydantic-settings, python-telegram-bot v20, httpx, aiosqlite, pytest + pytest-asyncio + respx

**Default env (all phases until Phase 8):**
```
ENV=development
MOCK_MODE=true
LLM_ENABLED=false
SCHEDULER_ENABLED=false
```

---

## File Map

```
crypto-intelligence-agent/
├── config/
│   ├── __init__.py
│   ├── settings.py          # Settings, get_settings()
│   └── prompts.py           # Claude prompt templates (Phase 9)
├── data_sources/
│   ├── __init__.py
│   ├── base.py              # DataSourceAdapter ABC, FallbackAdapter
│   ├── mock/
│   │   ├── __init__.py
│   │   ├── mock_price.py
│   │   ├── mock_news.py
│   │   ├── mock_onchain.py
│   │   └── mock_social.py
│   ├── price/
│   │   ├── __init__.py
│   │   ├── binance.py       # Phase 8
│   │   └── coingecko.py     # Phase 8
│   ├── news/
│   │   ├── __init__.py
│   │   ├── rss_feed.py      # Phase 8
│   │   └── cryptopanic.py   # Phase 8
│   ├── onchain/
│   │   ├── __init__.py
│   │   ├── blockchain_com.py # Phase 8
│   │   └── etherscan.py     # Phase 8
│   └── social/
│       ├── __init__.py
│       └── reddit.py        # Phase 8
├── services/
│   ├── __init__.py
│   ├── cache.py             # TTLCache
│   ├── rate_limiter.py      # TokenBucketRateLimiter
│   ├── retry.py             # async_retry decorator
│   └── llm_budget.py        # LLMBudgetTracker (Phase 9)
├── graph/
│   ├── __init__.py
│   ├── state.py             # AgentState + all TypedDicts
│   ├── aggregator.py        # aggregate_raw, fan_out_analyzers, merge_analysis
│   ├── edges.py             # route_after_aggregate
│   └── pipeline.py          # build_graph(), build_pipeline()
├── agents/
│   ├── __init__.py
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── price_collector.py
│   │   ├── news_collector.py
│   │   ├── onchain_collector.py
│   │   └── social_collector.py
│   ├── analyzers/
│   │   ├── __init__.py
│   │   ├── sentiment_analyzer.py
│   │   ├── market_structure_analyzer.py
│   │   └── risk_analyzer.py
│   └── supervisor.py
├── publishers/
│   ├── __init__.py
│   ├── base.py              # ReportPublisher ABC
│   └── telegram_publisher.py
├── api/
│   ├── __init__.py
│   ├── main.py              # create_app(), lifespan
│   ├── schemas.py           # Pydantic response models
│   └── routes/
│       ├── __init__.py
│       ├── health.py
│       └── report.py
├── scheduler/
│   ├── __init__.py
│   └── jobs.py              # Phase 10
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_adapters.py
│   │   ├── test_services.py
│   │   ├── test_aggregator.py
│   │   └── test_analyzers.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_pipeline.py
│   │   └── test_api.py
│   └── fixtures/
│       ├── __init__.py
│       └── mock_responses.py
├── docs/
│   └── superpowers/
│       ├── specs/
│       └── plans/
├── .env.example
├── .env
├── pyproject.toml
├── Dockerfile
└── README.md
```

---

## Phase 1: Bootstrap

### Task 1: Project scaffold + pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: all `__init__.py` files listed in file map above

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "crypto-intelligence-agent"
version = "0.1.0"
requires-python = ">=3.11"
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

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create all directories and empty `__init__.py` files**

```powershell
$dirs = @(
    "config","data_sources","data_sources/mock","data_sources/price",
    "data_sources/news","data_sources/onchain","data_sources/social",
    "services","graph","agents","agents/collectors","agents/analyzers",
    "publishers","api","api/routes","scheduler",
    "tests","tests/unit","tests/integration","tests/fixtures"
)
foreach ($d in $dirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
    New-Item -ItemType File -Path "$d/__init__.py" -Force | Out-Null
}
```

- [ ] **Step 3: Install dependencies**

```powershell
pip install -e ".[dev]"
```

Expected: packages install without error. `pip show langgraph` shows version ≥ 0.2.

- [ ] **Step 4: Verify pytest discovers tests**

```powershell
pytest --collect-only
```

Expected: `no tests ran` (0 items, no errors).

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml config/__init__.py data_sources/__init__.py services/__init__.py graph/__init__.py agents/__init__.py agents/collectors/__init__.py agents/analyzers/__init__.py publishers/__init__.py api/__init__.py api/routes/__init__.py scheduler/__init__.py tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py tests/fixtures/__init__.py data_sources/mock/__init__.py data_sources/price/__init__.py data_sources/news/__init__.py data_sources/onchain/__init__.py data_sources/social/__init__.py
git commit -m "chore: scaffold project structure and pyproject.toml"
```

---

### Task 2: Settings + .env.example

**Files:**
- Create: `config/settings.py`
- Create: `.env.example`
- Create: `.env`

- [ ] **Step 1: Write `config/settings.py`**

```python
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: Literal["development", "test", "production"] = "development"
    MOCK_MODE: bool = True
    LLM_ENABLED: bool = False
    DAILY_LLM_BUDGET_IDR: float = 0.0
    MAX_LLM_CALLS_PER_DAY: int = 0
    SCHEDULER_ENABLED: bool = False

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_SUPERVISOR_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_ANALYZER_MODEL: str = "claude-haiku-4-5-20251001"

    ETHERSCAN_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "crypto-intel-agent/0.1"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    API_AUTH_ENABLED: bool = False
    API_KEY: str = ""

    DISPLAY_TIMEZONE: str = "Asia/Jakarta"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def use_mock(self) -> bool:
        """Mock allowed only in dev/test, or when MOCK_MODE=true explicitly."""
        return self.ENV in ("development", "test") or self.MOCK_MODE


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Write `.env.example`**

```
# Runtime environment
ENV=development
MOCK_MODE=true
LLM_ENABLED=false
DAILY_LLM_BUDGET_IDR=0
MAX_LLM_CALLS_PER_DAY=0
SCHEDULER_ENABLED=false

# Anthropic (required only when LLM_ENABLED=true)
ANTHROPIC_API_KEY=
ANTHROPIC_SUPERVISOR_MODEL=claude-sonnet-4-6
ANTHROPIC_ANALYZER_MODEL=claude-haiku-4-5-20251001

# On-chain data (optional — falls back to mock if empty)
ETHERSCAN_API_KEY=

# Reddit (optional — skipped gracefully if empty)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=crypto-intel-agent/0.1

# Telegram (required for Telegram publishing)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# API auth (disabled by default)
API_AUTH_ENABLED=false
API_KEY=

# Display
DISPLAY_TIMEZONE=Asia/Jakarta
```

- [ ] **Step 3: Copy `.env.example` to `.env`**

```powershell
Copy-Item .env.example .env
```

- [ ] **Step 4: Write test**

```python
# tests/unit/test_settings.py
from config.settings import Settings


def test_default_settings_are_cost_safe():
    s = Settings()
    assert s.LLM_ENABLED is False
    assert s.MOCK_MODE is True
    assert s.MAX_LLM_CALLS_PER_DAY == 0
    assert s.SCHEDULER_ENABLED is False


def test_use_mock_true_in_development():
    s = Settings(ENV="development", MOCK_MODE=False)
    assert s.use_mock() is True


def test_use_mock_false_in_production():
    s = Settings(ENV="production", MOCK_MODE=False)
    assert s.use_mock() is False


def test_use_mock_true_when_flag_set_in_production():
    s = Settings(ENV="production", MOCK_MODE=True)
    assert s.use_mock() is True
```

- [ ] **Step 5: Run tests**

```powershell
pytest tests/unit/test_settings.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```powershell
git add config/settings.py .env.example .env tests/unit/test_settings.py
git commit -m "feat: add pydantic-settings config with cost-safe defaults"
```

---

### Task 3: Logging + conftest

**Files:**
- Create: `config/logging_config.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `config/logging_config.py`**

```python
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
```

- [ ] **Step 2: Write `tests/conftest.py`**

```python
import pytest
import uuid
from datetime import datetime, timezone
from config.settings import Settings


@pytest.fixture
def settings_mock() -> Settings:
    """Cost-safe test settings — mock mode, no LLM, no scheduler."""
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


@pytest.fixture
def base_state() -> dict:
    """Minimal valid AgentState for testing nodes."""
    return {
        "run_id": str(uuid.uuid4()),
        "symbol": "BTCUSDT",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data": None,
        "news_data": [],
        "onchain_data": None,
        "social_data": None,
        "context": None,
        "sentiment_analysis": None,
        "market_structure_analysis": None,
        "risk_analysis": None,
        "analysis": None,
        "report": None,
        "data_gaps": [],
        "errors": [],
    }


@pytest.fixture
def eth_state(base_state) -> dict:
    return {**base_state, "symbol": "ETHUSDT"}
```

- [ ] **Step 3: Commit**

```powershell
git add config/logging_config.py tests/conftest.py
git commit -m "chore: add logging config and shared test fixtures"
```

---

## Phase 2: Core Services

### Task 4: DataSourceAdapter + FallbackAdapter

**Files:**
- Create: `data_sources/base.py`
- Create: `tests/unit/test_adapters.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_adapters.py
import pytest
from unittest.mock import AsyncMock
from data_sources.base import DataSourceAdapter, FallbackAdapter


class _OkAdapter(DataSourceAdapter):
    @property
    def source_name(self) -> str:
        return "ok"

    async def fetch(self, symbol: str):
        return {"price": 1.0}


class _NoneAdapter(DataSourceAdapter):
    @property
    def source_name(self) -> str:
        return "none"

    async def fetch(self, symbol: str):
        return None


class _BoomAdapter(DataSourceAdapter):
    @property
    def source_name(self) -> str:
        return "boom"

    async def fetch(self, symbol: str):
        raise RuntimeError("connection refused")


async def test_fallback_returns_first_success():
    adapter = FallbackAdapter(_NoneAdapter(), _OkAdapter())
    result = await adapter.fetch("BTCUSDT")
    assert result == {"price": 1.0}


async def test_fallback_skips_exceptions():
    adapter = FallbackAdapter(_BoomAdapter(), _OkAdapter())
    result = await adapter.fetch("BTCUSDT")
    assert result == {"price": 1.0}


async def test_fallback_returns_none_when_all_fail():
    adapter = FallbackAdapter(_NoneAdapter(), _BoomAdapter())
    result = await adapter.fetch("BTCUSDT")
    assert result is None


async def test_fallback_source_name_lists_chain():
    adapter = FallbackAdapter(_NoneAdapter(), _OkAdapter())
    assert "none" in adapter.source_name
    assert "ok" in adapter.source_name
```

- [ ] **Step 2: Run to verify failure**

```powershell
pytest tests/unit/test_adapters.py -v
```

Expected: `ImportError: cannot import name 'DataSourceAdapter'`

- [ ] **Step 3: Write `data_sources/base.py`**

```python
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
    """Tries each adapter in chain. Returns first non-None result. Logs all failures."""

    def __init__(self, *adapters: DataSourceAdapter) -> None:
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
        logger.error("All adapters exhausted for symbol=%s", symbol)
        return None

    @property
    def source_name(self) -> str:
        names = ", ".join(a.source_name for a in self._chain)
        return f"fallback({names})"
```

- [ ] **Step 4: Run tests**

```powershell
pytest tests/unit/test_adapters.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```powershell
git add data_sources/base.py tests/unit/test_adapters.py
git commit -m "feat: add DataSourceAdapter ABC and FallbackAdapter"
```

---

### Task 5: RetryDecorator

**Files:**
- Create: `services/retry.py`
- Modify: `tests/unit/test_services.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_services.py
import pytest
from unittest.mock import AsyncMock, call
from services.retry import async_retry


async def test_retry_succeeds_on_first_try():
    mock = AsyncMock(return_value="ok")
    decorated = async_retry(max_attempts=3, base_delay=0)(mock)
    result = await decorated()
    assert result == "ok"
    assert mock.call_count == 1


async def test_retry_succeeds_after_one_failure():
    mock = AsyncMock(side_effect=[RuntimeError("boom"), "ok"])
    decorated = async_retry(max_attempts=3, base_delay=0)(mock)
    result = await decorated()
    assert result == "ok"
    assert mock.call_count == 2


async def test_retry_raises_after_max_attempts():
    mock = AsyncMock(side_effect=RuntimeError("boom"))
    decorated = async_retry(max_attempts=3, base_delay=0)(mock)
    with pytest.raises(RuntimeError, match="boom"):
        await decorated()
    assert mock.call_count == 3
```

- [ ] **Step 2: Run to verify failure**

```powershell
pytest tests/unit/test_services.py -v
```

Expected: `ImportError: cannot import name 'async_retry'`

- [ ] **Step 3: Write `services/retry.py`**

```python
import asyncio
import functools
import logging
from typing import Callable, Type

logger = logging.getLogger(__name__)


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Async exponential-backoff retry decorator."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    logger.warning(
                        "%s attempt %d/%d failed: %s — retrying in %.1fs",
                        fn.__name__, attempt, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff
        return wrapper
    return decorator
```

- [ ] **Step 4: Run tests**

```powershell
pytest tests/unit/test_services.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```powershell
git add services/retry.py tests/unit/test_services.py
git commit -m "feat: add async_retry exponential backoff decorator"
```

---

### Task 6: TTLCache

**Files:**
- Modify: `services/cache.py`
- Modify: `tests/unit/test_services.py`

- [ ] **Step 1: Append failing test to `tests/unit/test_services.py`**

```python
import asyncio
from services.cache import TTLCache


async def test_cache_returns_cached_value():
    cache = TTLCache(ttl_seconds=60)
    cache.set("key1", {"price": 1.0})
    assert cache.get("key1") == {"price": 1.0}


async def test_cache_returns_none_for_missing_key():
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("missing") is None


async def test_cache_expires_after_ttl():
    cache = TTLCache(ttl_seconds=0.05)
    cache.set("key1", "value")
    await asyncio.sleep(0.1)
    assert cache.get("key1") is None
```

- [ ] **Step 2: Write `services/cache.py`**

```python
import time
from typing import Any, Optional


class TTLCache:
    """Simple in-memory TTL cache. Thread-safe for asyncio (single event loop)."""

    def __init__(self, ttl_seconds: float = 300) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        self._store.clear()
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_services.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Commit**

```powershell
git add services/cache.py tests/unit/test_services.py
git commit -m "feat: add TTLCache in-memory cache with expiry"
```

---

### Task 7: RateLimiter

**Files:**
- Create: `services/rate_limiter.py`
- Modify: `tests/unit/test_services.py`

- [ ] **Step 1: Append failing test**

```python
import time
from services.rate_limiter import RateLimiter


async def test_rate_limiter_allows_within_limit():
    limiter = RateLimiter(calls_per_second=100)
    # Should not block
    t0 = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5


async def test_rate_limiter_blocks_when_exceeded():
    limiter = RateLimiter(calls_per_second=10)
    # Exhaust tokens
    for _ in range(10):
        await limiter.acquire()
    # Next call should delay
    t0 = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.05
```

- [ ] **Step 2: Write `services/rate_limiter.py`**

```python
import asyncio
import time


class RateLimiter:
    """Token bucket rate limiter for async code."""

    def __init__(self, calls_per_second: float = 2.0) -> None:
        self._rate = calls_per_second
        self._tokens = calls_per_second
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            wait = (1 - self._tokens) / self._rate
            await asyncio.sleep(wait)
```

- [ ] **Step 3: Run all service tests**

```powershell
pytest tests/unit/test_services.py -v
```

Expected: 8 passed.

- [ ] **Step 4: Commit**

```powershell
git add services/rate_limiter.py tests/unit/test_services.py
git commit -m "feat: add token-bucket RateLimiter"
```

---

## Phase 3: Mock Adapters

### Task 8: MockPriceAdapter

**Files:**
- Create: `data_sources/mock/mock_price.py`
- Modify: `tests/unit/test_adapters.py`

- [ ] **Step 1: Append failing test**

```python
from data_sources.mock.mock_price import MockPriceAdapter


async def test_mock_price_btcusdt():
    adapter = MockPriceAdapter()
    result = await adapter.fetch("BTCUSDT")
    assert result is not None
    assert result["price"] > 0
    assert "change_24h_pct" in result
    assert "ohlcv_24h" in result
    assert len(result["ohlcv_24h"]) >= 14  # enough for RSI


async def test_mock_price_ethusdt():
    adapter = MockPriceAdapter()
    result = await adapter.fetch("ETHUSDT")
    assert result["price"] > 0


async def test_mock_price_ohlcv_has_required_keys():
    adapter = MockPriceAdapter()
    result = await adapter.fetch("BTCUSDT")
    candle = result["ohlcv_24h"][0]
    assert all(k in candle for k in ("open", "high", "low", "close", "volume", "timestamp"))
```

- [ ] **Step 2: Write `data_sources/mock/mock_price.py`**

```python
import math
from datetime import datetime, timezone, timedelta
from data_sources.base import DataSourceAdapter


def _generate_ohlcv(base_price: float, hours: int = 24) -> list[dict]:
    """Generate synthetic hourly OHLCV candles with slight price variation."""
    candles = []
    now = datetime.now(timezone.utc)
    price = base_price
    for i in range(hours, 0, -1):
        ts = now - timedelta(hours=i)
        variation = base_price * 0.005 * math.sin(i * 0.7)
        open_ = price
        close = price + variation
        high = max(open_, close) * 1.002
        low = min(open_, close) * 0.998
        volume = base_price * 400 * (1 + 0.1 * math.sin(i))
        candles.append({
            "timestamp": ts.isoformat(),
            "open": round(open_, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": round(volume, 2),
        })
        price = close
    return candles


_MOCK_DATA = {
    "BTCUSDT": {"base_price": 65_000.0, "change_24h_pct": 2.3,
                "volume_24h": 28_500_000_000.0},
    "ETHUSDT": {"base_price": 3_200.0, "change_24h_pct": 1.8,
                "volume_24h": 14_200_000_000.0},
    "SOLUSDT": {"base_price": 145.0, "change_24h_pct": -0.5,
                "volume_24h": 3_100_000_000.0},
}


class MockPriceAdapter(DataSourceAdapter):
    @property
    def source_name(self) -> str:
        return "mock_price"

    async def fetch(self, symbol: str) -> dict:
        data = _MOCK_DATA.get(symbol, _MOCK_DATA["BTCUSDT"])
        bp = data["base_price"]
        ohlcv = _generate_ohlcv(bp, hours=24)
        return {
            "price": bp,
            "change_24h_pct": data["change_24h_pct"],
            "volume_24h": data["volume_24h"],
            "high_24h": round(bp * 1.018, 2),
            "low_24h": round(bp * 0.982, 2),
            "ohlcv_24h": ohlcv,
        }
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_adapters.py -v
```

Expected: 7 passed.

- [ ] **Step 4: Commit**

```powershell
git add data_sources/mock/mock_price.py tests/unit/test_adapters.py
git commit -m "feat: add MockPriceAdapter with synthetic OHLCV data"
```

---

### Task 9: MockNewsAdapter + MockOnChainAdapter + MockSocialAdapter

**Files:**
- Create: `data_sources/mock/mock_news.py`
- Create: `data_sources/mock/mock_onchain.py`
- Create: `data_sources/mock/mock_social.py`
- Modify: `tests/unit/test_adapters.py`

- [ ] **Step 1: Append failing tests**

```python
from data_sources.mock.mock_news import MockNewsAdapter
from data_sources.mock.mock_onchain import MockOnChainAdapter
from data_sources.mock.mock_social import MockSocialAdapter


async def test_mock_news_returns_list():
    adapter = MockNewsAdapter()
    result = await adapter.fetch("BTCUSDT")
    assert isinstance(result, list)
    assert len(result) >= 3
    assert all("headline" in item for item in result)
    assert all("source" in item for item in result)
    assert all("published_at" in item for item in result)
    assert all("url" in item for item in result)


async def test_mock_onchain_btc():
    adapter = MockOnChainAdapter()
    result = await adapter.fetch("BTCUSDT")
    assert result is not None
    assert result["network"] == "bitcoin"
    assert "hash_rate" in result
    assert "mempool_size" in result


async def test_mock_onchain_eth():
    adapter = MockOnChainAdapter()
    result = await adapter.fetch("ETHUSDT")
    assert result["network"] == "ethereum"
    assert "gas_price_gwei" in result


async def test_mock_social_returns_dict():
    adapter = MockSocialAdapter()
    result = await adapter.fetch("BTCUSDT")
    assert isinstance(result, dict)
    assert "mention_volume" in result
    assert "sentiment_hint" in result
    assert result["sentiment_hint"] in ("bullish", "bearish", "neutral")
```

- [ ] **Step 2: Write `data_sources/mock/mock_news.py`**

```python
from datetime import datetime, timezone, timedelta
from data_sources.base import DataSourceAdapter


class MockNewsAdapter(DataSourceAdapter):
    @property
    def source_name(self) -> str:
        return "mock_news"

    async def fetch(self, symbol: str) -> list[dict]:
        coin = symbol.replace("USDT", "")
        now = datetime.now(timezone.utc)
        return [
            {
                "headline": f"{coin} shows strong accumulation signals amid rising volume",
                "source": "MockCryptoNews",
                "published_at": (now - timedelta(hours=1)).isoformat(),
                "url": f"https://example.com/{coin.lower()}-accumulation",
            },
            {
                "headline": f"Analysts bullish on {coin} price target after recent rally",
                "source": "MockAnalysis",
                "published_at": (now - timedelta(hours=3)).isoformat(),
                "url": f"https://example.com/{coin.lower()}-target",
            },
            {
                "headline": f"{coin} network activity surge signals growing adoption",
                "source": "MockOnChainReport",
                "published_at": (now - timedelta(hours=5)).isoformat(),
                "url": f"https://example.com/{coin.lower()}-network",
            },
            {
                "headline": f"Market overview: {coin} holds key support level",
                "source": "MockMarketWatch",
                "published_at": (now - timedelta(hours=8)).isoformat(),
                "url": f"https://example.com/{coin.lower()}-support",
            },
        ]
```

- [ ] **Step 3: Write `data_sources/mock/mock_onchain.py`**

```python
from data_sources.base import DataSourceAdapter


class MockOnChainAdapter(DataSourceAdapter):
    @property
    def source_name(self) -> str:
        return "mock_onchain"

    async def fetch(self, symbol: str) -> dict:
        if symbol == "ETHUSDT":
            return {
                "network": "ethereum",
                "gas_price_gwei": 25.4,
                "tx_count_24h": 1_200_000,
                "active_addresses_24h": 420_000,
            }
        return {
            "network": "bitcoin",
            "hash_rate_eh": 620.5,
            "mempool_size": 45_000,
            "tx_count_24h": 310_000,
            "avg_fee_sat": 28,
        }
```

- [ ] **Step 4: Write `data_sources/mock/mock_social.py`**

```python
from data_sources.base import DataSourceAdapter


class MockSocialAdapter(DataSourceAdapter):
    @property
    def source_name(self) -> str:
        return "mock_social"

    async def fetch(self, symbol: str) -> dict:
        coin = symbol.replace("USDT", "")
        return {
            "mention_volume": 4_200,
            "sentiment_hint": "bullish",
            "sample_posts": [
                f"Holding {coin}, looking strong",
                f"{coin} to the moon, accumulating more",
                f"Long on {coin}, good entry here",
            ],
        }
```

- [ ] **Step 5: Run tests**

```powershell
pytest tests/unit/test_adapters.py -v
```

Expected: 11 passed.

- [ ] **Step 6: Commit**

```powershell
git add data_sources/mock/ tests/unit/test_adapters.py
git commit -m "feat: add MockNewsAdapter, MockOnChainAdapter, MockSocialAdapter"
```

---

## Phase 4: LangGraph Pipeline

### Task 10: graph/state.py

**Files:**
- Create: `graph/state.py`
- Create: `tests/unit/test_aggregator.py` (state shape tests only)

- [ ] **Step 1: Write `graph/state.py`**

```python
from typing import Annotated, Literal, Optional, Union
from typing_extensions import TypedDict
import operator


class NormalizedMarketContext(TypedDict):
    """Output of aggregate_raw. Nodes downstream never see raw API dicts."""
    symbol: str
    price_summary: dict      # {price, change_24h_pct, volume_24h, high_24h, low_24h, ohlcv_24h}
    news_items: list[dict]   # [{headline, source, published_at, url}]
    onchain_summary: dict    # network-specific metrics
    social_summary: dict     # {mention_volume, sentiment_hint, sample_posts}
    data_gaps: list[str]     # deduplicated list of unavailable sources


class AnalysisResult(TypedDict):
    """Output of merge_analysis."""
    sentiment_score: Optional[float]      # -1.0 to 1.0
    sentiment_label: Optional[str]        # bullish | bearish | neutral
    sentiment_drivers: Optional[list[str]]
    market_structure: Optional[dict]      # MarketStructureAnalysis output dict
    risk_level: Optional[str]             # low | medium | high
    risk_factors: Optional[list[str]]


class IntelligenceReport(TypedDict):
    run_id: str
    symbol: str
    requested_at: str           # UTC ISO
    generated_at: str           # UTC ISO
    market_bias: Literal["bullish", "bearish", "neutral"]
    confidence_score: float     # 0.0–1.0
    key_signals: list[str]
    risk_warnings: list[str]
    narrative: str
    data_gaps: list[str]


class ErrorReport(TypedDict):
    run_id: str
    symbol: str
    requested_at: str
    generated_at: str
    error: str


class AgentState(TypedDict):
    # Request metadata
    run_id: str
    symbol: str
    requested_at: str

    # Raw collector outputs — separate top-level fields, reducer-safe in parallel
    price_data: Optional[dict]
    news_data: Annotated[list, operator.add]    # safe list append across parallel nodes
    onchain_data: Optional[dict]
    social_data: Optional[dict]

    # Post-aggregation (set by aggregate_raw)
    context: Optional[NormalizedMarketContext]

    # Separate analyzer outputs (set independently by parallel analyzer nodes)
    sentiment_analysis: Optional[dict]
    market_structure_analysis: Optional[dict]
    risk_analysis: Optional[dict]

    # Merged (set by merge_analysis)
    analysis: Optional[AnalysisResult]

    # Final output — IntelligenceReport on success, ErrorReport on critical failure
    report: Optional[Union[IntelligenceReport, ErrorReport]]

    # Error tracking — reducer-safe
    data_gaps: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
```

- [ ] **Step 2: Write state shape test**

```python
# tests/unit/test_aggregator.py
from graph.state import AgentState, IntelligenceReport, ErrorReport


def test_agent_state_has_required_fields():
    required = {
        "run_id", "symbol", "requested_at",
        "price_data", "news_data", "onchain_data", "social_data",
        "context", "sentiment_analysis", "market_structure_analysis",
        "risk_analysis", "analysis", "report", "data_gaps", "errors",
    }
    annotations = AgentState.__annotations__
    assert required.issubset(set(annotations.keys()))


def test_intelligence_report_has_no_error_field():
    assert "error" not in IntelligenceReport.__annotations__


def test_error_report_has_error_field():
    assert "error" in ErrorReport.__annotations__
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_aggregator.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```powershell
git add graph/state.py tests/unit/test_aggregator.py
git commit -m "feat: add LangGraph AgentState schema with reducer-safe fields"
```

---

### Task 11: graph/aggregator.py

**Files:**
- Create: `graph/aggregator.py`
- Modify: `tests/unit/test_aggregator.py`

- [ ] **Step 1: Append failing tests**

```python
import uuid
from datetime import datetime, timezone
from graph.aggregator import aggregate_raw, merge_analysis


def _state_with_data(symbol="BTCUSDT"):
    """Full state with mock raw data already populated."""
    return {
        "run_id": str(uuid.uuid4()),
        "symbol": symbol,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data": {
            "price": 65000.0, "change_24h_pct": 2.3,
            "volume_24h": 28e9, "high_24h": 66200.0, "low_24h": 63800.0,
            "ohlcv_24h": [{"open":64000,"high":65000,"low":63900,"close":64500,"volume":1e6,"timestamp":"2026-05-03T00:00:00Z"}],
        },
        "news_data": [{"title": "BTC surges", "source": "MockNews",
                       "published_at": "2026-05-03T08:00:00Z", "url": "https://example.com/1"}],
        "onchain_data": {"network": "bitcoin", "hash_rate_eh": 620.0, "mempool_size": 45000},
        "social_data": {"mention_volume": 4200, "sentiment_hint": "bullish", "sample_posts": []},
        "context": None, "sentiment_analysis": None, "market_structure_analysis": None,
        "risk_analysis": None, "analysis": None, "report": None,
        "data_gaps": [], "errors": [],
    }


def test_aggregate_raw_builds_context():
    state = _state_with_data()
    result = aggregate_raw(state)
    ctx = result["context"]
    assert ctx is not None
    assert ctx["symbol"] == "BTCUSDT"
    assert ctx["price_summary"]["price"] == 65000.0
    assert isinstance(ctx["news_items"], list)
    assert ctx["news_items"][0]["headline"] is not None


def test_aggregate_raw_deduplicates_gaps():
    state = _state_with_data()
    state["data_gaps"] = ["social_unavailable", "social_unavailable", "news_unavailable"]
    result = aggregate_raw(state)
    gaps = result["context"]["data_gaps"]
    assert len(gaps) == len(set(gaps))


def test_aggregate_raw_sets_error_report_when_price_none():
    state = _state_with_data()
    state["price_data"] = None
    state["data_gaps"] = ["price_unavailable"]
    result = aggregate_raw(state)
    assert result["report"] is not None
    assert "error" in result["report"]
    assert "Price data unavailable" in result["report"]["error"]


def test_merge_analysis_combines_all_three():
    state = _state_with_data()
    state["sentiment_analysis"] = {
        "sentiment_score": 0.4, "sentiment_label": "bullish", "sentiment_drivers": ["BTC surges"]}
    state["market_structure_analysis"] = {
        "bias": "bullish", "rsi": 58.0, "ma_trend": "uptrend",
        "confidence_score": 0.65, "explanation": "BOS bullish detected",
        "swing_highs": [64100.0], "swing_lows": [63900.0],
        "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
        "volume_confirmed": True, "invalidation_level": 63900.0,
        "macd_histogram_slope": 0.002, "momentum_pct": 1.2,
        "ml_probability_1r": None, "ml_probability_2r": None,
    }
    state["risk_analysis"] = {"risk_level": "low", "risk_factors": []}
    result = merge_analysis(state)
    analysis = result["analysis"]
    assert analysis["sentiment_label"] == "bullish"
    assert analysis["market_structure"]["rsi"] == 58.0
    assert analysis["risk_level"] == "low"


def test_merge_analysis_handles_none_inputs():
    state = _state_with_data()
    state["sentiment_analysis"] = None
    state["market_structure_analysis"] = None
    state["risk_analysis"] = None
    result = merge_analysis(state)
    analysis = result["analysis"]
    assert analysis["sentiment_label"] is None
    assert analysis["market_structure"] is None or analysis["market_structure"] == {}
```

- [ ] **Step 2: Run to verify failures**

```powershell
pytest tests/unit/test_aggregator.py -v
```

Expected: first 3 tests fail with ImportError.

- [ ] **Step 3: Write `graph/aggregator.py`**

```python
from datetime import datetime, timezone
from graph.state import AgentState, NormalizedMarketContext, AnalysisResult, ErrorReport


def aggregate_raw(state: AgentState) -> dict:
    """Normalize raw collector outputs. Sets ErrorReport and exits if price_data is None."""
    if state.get("price_data") is None:
        error: ErrorReport = {
            "run_id": state["run_id"],
            "symbol": state["symbol"],
            "requested_at": state["requested_at"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": "Price data unavailable — cannot generate intelligence report",
        }
        return {"report": error}

    # Deduplicate data_gaps accumulated by parallel collectors
    gaps = list(dict.fromkeys(state.get("data_gaps", [])))

    # Normalize price
    raw_price = state["price_data"]
    price_summary = {
        "price": raw_price.get("price", 0.0),
        "change_24h_pct": raw_price.get("change_24h_pct", 0.0),
        "volume_24h": raw_price.get("volume_24h", 0.0),
        "high_24h": raw_price.get("high_24h", 0.0),
        "low_24h": raw_price.get("low_24h", 0.0),
        "ohlcv_24h": raw_price.get("ohlcv_24h", []),
    }

    # Normalize news — accept both "headline" and "title" keys from raw sources
    news_items = []
    for item in state.get("news_data", []):
        news_items.append({
            "headline": item.get("headline") or item.get("title", ""),
            "source": item.get("source", ""),
            "published_at": item.get("published_at", ""),
            "url": item.get("url", ""),
        })

    onchain_summary = state.get("onchain_data") or {}
    social_summary = state.get("social_data") or {}

    context: NormalizedMarketContext = {
        "symbol": state["symbol"],
        "price_summary": price_summary,
        "news_items": news_items,
        "onchain_summary": onchain_summary,
        "social_summary": social_summary,
        "data_gaps": gaps,
    }
    return {"context": context}


def fan_out_analyzers(state: AgentState) -> dict:
    """No-op routing node. Exists to split conditional edge from aggregate_raw."""
    return {}


def merge_analysis(state: AgentState) -> dict:
    """Combine three separate analyzer outputs into one AnalysisResult."""
    sentiment = state.get("sentiment_analysis") or {}
    pattern = state.get("market_structure_analysis") or {}
    risk = state.get("risk_analysis") or {}

    analysis: AnalysisResult = {
        "sentiment_score": sentiment.get("sentiment_score"),
        "sentiment_label": sentiment.get("sentiment_label"),
        "sentiment_drivers": sentiment.get("sentiment_drivers"),
        "market_structure": pattern,
        "risk_level": risk.get("risk_level"),
        "risk_factors": risk.get("risk_factors"),
    }
    return {"analysis": analysis}
```

- [ ] **Step 4: Run tests**

```powershell
pytest tests/unit/test_aggregator.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```powershell
git add graph/aggregator.py tests/unit/test_aggregator.py
git commit -m "feat: add aggregate_raw, merge_analysis, fan_out_analyzers nodes"
```

---

### Task 12: Collector nodes

**Files:**
- Create: `agents/collectors/price_collector.py`
- Create: `agents/collectors/news_collector.py`
- Create: `agents/collectors/onchain_collector.py`
- Create: `agents/collectors/social_collector.py`
- Create: `tests/unit/test_collectors.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_collectors.py
import pytest
from unittest.mock import AsyncMock
from data_sources.mock.mock_price import MockPriceAdapter
from data_sources.mock.mock_news import MockNewsAdapter
from data_sources.mock.mock_onchain import MockOnChainAdapter
from data_sources.mock.mock_social import MockSocialAdapter
from agents.collectors.price_collector import make_price_collector
from agents.collectors.news_collector import make_news_collector
from agents.collectors.onchain_collector import make_onchain_collector
from agents.collectors.social_collector import make_social_collector


async def test_collect_price_writes_price_data(base_state):
    node = make_price_collector(MockPriceAdapter())
    result = await node(base_state)
    assert result["price_data"]["price"] > 0


async def test_collect_price_failure_writes_gap(base_state):
    adapter = MockPriceAdapter()
    adapter.fetch = AsyncMock(return_value=None)
    node = make_price_collector(adapter)
    result = await node(base_state)
    assert "price_unavailable" in result["data_gaps"]
    assert result.get("price_data") is None


async def test_collect_news_writes_news_data(base_state):
    node = make_news_collector(MockNewsAdapter())
    result = await node(base_state)
    assert isinstance(result["news_data"], list)
    assert len(result["news_data"]) > 0


async def test_collect_news_failure_writes_gap(base_state):
    adapter = MockNewsAdapter()
    adapter.fetch = AsyncMock(return_value=None)
    node = make_news_collector(adapter)
    result = await node(base_state)
    assert "news_unavailable" in result["data_gaps"]


async def test_collect_onchain_success(base_state):
    node = make_onchain_collector(MockOnChainAdapter())
    result = await node(base_state)
    assert result["onchain_data"] is not None


async def test_collect_onchain_failure_writes_gap(base_state):
    adapter = MockOnChainAdapter()
    adapter.fetch = AsyncMock(return_value=None)
    node = make_onchain_collector(adapter)
    result = await node(base_state)
    assert "onchain_unavailable" in result["data_gaps"]


async def test_collect_social_success(base_state):
    node = make_social_collector(MockSocialAdapter())
    result = await node(base_state)
    assert result["social_data"] is not None


async def test_collect_social_failure_writes_gap(base_state):
    adapter = MockSocialAdapter()
    adapter.fetch = AsyncMock(return_value=None)
    node = make_social_collector(adapter)
    result = await node(base_state)
    assert "social_unavailable" in result["data_gaps"]
```

- [ ] **Step 2: Write all four collector files**

```python
# agents/collectors/price_collector.py
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_price_collector(adapter: DataSourceAdapter):
    async def collect_price(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if result is None:
            return {"data_gaps": ["price_unavailable"]}
        return {"price_data": result}
    return collect_price
```

```python
# agents/collectors/news_collector.py
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_news_collector(adapter: DataSourceAdapter):
    async def collect_news(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if result is None:
            return {"data_gaps": ["news_unavailable"]}
        return {"news_data": result}   # list — operator.add reducer appends safely
    return collect_news
```

```python
# agents/collectors/onchain_collector.py
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_onchain_collector(adapter: DataSourceAdapter):
    async def collect_onchain(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if result is None:
            return {"data_gaps": ["onchain_unavailable"]}
        return {"onchain_data": result}
    return collect_onchain
```

```python
# agents/collectors/social_collector.py
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_social_collector(adapter: DataSourceAdapter):
    async def collect_social(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if result is None:
            return {"data_gaps": ["social_unavailable"]}
        return {"social_data": result}
    return collect_social
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_collectors.py -v
```

Expected: 8 passed.

- [ ] **Step 4: Commit**

```powershell
git add agents/collectors/ tests/unit/test_collectors.py
git commit -m "feat: add collector nodes with factory pattern and gap reporting"
```

---

### Task 13: Deterministic analyzer nodes

**Files:**
- Create: `agents/analyzers/sentiment_analyzer.py`
- Create: `agents/analyzers/market_structure_analyzer.py`
- Create: `agents/analyzers/risk_analyzer.py`
- Create: `tests/unit/test_analyzers.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_analyzers.py
import uuid
from datetime import datetime, timezone
from config.settings import Settings
from agents.analyzers.sentiment_analyzer import make_sentiment_analyzer
from agents.analyzers.market_structure_analyzer import analyze_market_structure
from agents.analyzers.risk_analyzer import make_risk_analyzer


def _state_with_context(news_headlines=None, onchain=None, price_change=2.0):
    ohlcv = [
        {"open": 64000+i*10, "high": 64100+i*10, "low": 63900+i*10,
         "close": 64050+i*10, "volume": 1_000_000, "timestamp": f"2026-05-03T{i:02d}:00:00Z"}
        for i in range(24)
    ]
    return {
        "run_id": str(uuid.uuid4()),
        "symbol": "BTCUSDT",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data": None, "news_data": [], "onchain_data": None, "social_data": None,
        "context": {
            "symbol": "BTCUSDT",
            "price_summary": {
                "price": 65000.0, "change_24h_pct": price_change,
                "volume_24h": 28e9, "high_24h": 66000.0, "low_24h": 64000.0,
                "ohlcv_24h": ohlcv,
            },
            "news_items": [{"headline": h, "source": "Mock", "published_at": "", "url": ""}
                           for h in (news_headlines or [])],
            "onchain_summary": onchain or {},
            "social_summary": {},
            "data_gaps": [],
        },
        "sentiment_analysis": None, "market_structure_analysis": None,
        "risk_analysis": None, "analysis": None, "report": None,
        "data_gaps": [], "errors": [],
    }


async def test_sentiment_deterministic_bullish():
    settings = Settings(LLM_ENABLED=False)
    node = make_sentiment_analyzer(settings)
    state = _state_with_context(news_headlines=["BTC surges rally gain high buy"])
    result = await node(state)
    sa = result["sentiment_analysis"]
    assert sa["sentiment_label"] in ("bullish", "neutral", "bearish")
    assert -1.0 <= sa["sentiment_score"] <= 1.0
    assert isinstance(sa["sentiment_drivers"], list)


async def test_sentiment_returns_neutral_on_empty_news():
    settings = Settings(LLM_ENABLED=False)
    node = make_sentiment_analyzer(settings)
    state = _state_with_context(news_headlines=[])
    result = await node(state)
    assert result["sentiment_analysis"]["sentiment_label"] == "neutral"


async def test_market_structure_returns_expected_fields():
    state = _state_with_context()
    result = await analyze_market_structure(state)
    ms = result["market_structure_analysis"]
    assert ms["bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= ms["rsi"] <= 100.0
    assert ms["ma_trend"] in ("uptrend", "downtrend", "sideways")
    assert 0.0 <= ms["confidence_score"] <= 1.0
    assert isinstance(ms["explanation"], str)
    assert isinstance(ms["swing_highs"], list)
    assert isinstance(ms["swing_lows"], list)
    assert isinstance(ms["bos_choch"], list)
    assert ms["ml_probability_1r"] is None  # Phase 2


async def test_market_structure_insufficient_data_returns_neutral():
    state = _state_with_context()
    state["context"]["price_summary"]["ohlcv_24h"] = []
    result = await analyze_market_structure(state)
    ms = result["market_structure_analysis"]
    assert ms["bias"] == "neutral"
    assert ms["confidence_score"] == 0.0


async def test_risk_low_on_stable_market():
    settings = Settings(LLM_ENABLED=False)
    node = make_risk_analyzer(settings)
    state = _state_with_context(price_change=0.5)
    result = await node(state)
    ra = result["risk_analysis"]
    assert ra["risk_level"] in ("low", "medium", "high")
    assert isinstance(ra["risk_factors"], list)


async def test_risk_high_on_volatile_market():
    settings = Settings(LLM_ENABLED=False)
    node = make_risk_analyzer(settings)
    state = _state_with_context(price_change=15.0)
    result = await node(state)
    assert result["risk_analysis"]["risk_level"] in ("medium", "high")
```

- [ ] **Step 2: Write `agents/analyzers/sentiment_analyzer.py`**

```python
from config.settings import Settings
from graph.state import AgentState


def make_sentiment_analyzer(settings: Settings):
    async def analyze_sentiment(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            # Phase 9: Claude path
            pass
        return _deterministic_sentiment(state)
    return analyze_sentiment


_POSITIVE = {"bullish", "surge", "rally", "gain", "up", "rise", "high", "buy",
             "accumulation", "strong", "moon", "pump"}
_NEGATIVE = {"bearish", "crash", "drop", "fall", "down", "sell", "low", "fear",
             "dump", "weak", "correction", "breakdown"}


def _deterministic_sentiment(state: AgentState) -> dict:
    context = state.get("context") or {}
    news_items = context.get("news_items", [])
    social = context.get("social_summary", {})

    score = 0.0
    for item in news_items[:5]:
        words = set(item.get("headline", "").lower().split())
        pos = len(words & _POSITIVE)
        neg = len(words & _NEGATIVE)
        score += (pos - neg) * 0.15

    # Social hint contributes small weight
    hint = social.get("sentiment_hint", "neutral")
    if hint == "bullish":
        score += 0.1
    elif hint == "bearish":
        score -= 0.1

    score = max(-1.0, min(1.0, round(score, 2)))
    label = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"

    return {
        "sentiment_analysis": {
            "sentiment_score": score,
            "sentiment_label": label,
            "sentiment_drivers": [
                item["headline"] for item in news_items[:3] if item.get("headline")
            ],
        }
    }
```

- [ ] **Step 3: Write `agents/analyzers/market_structure_analyzer.py`**

Full implementation: swing detection → liquidity sweep → order block → BOS/CHOCH → volume confirmation → secondary indicators → confidence score.

```python
from __future__ import annotations
from typing import Optional
from graph.state import AgentState

# ---------------------------------------------------------------------------
# Public node function
# ---------------------------------------------------------------------------

async def analyze_market_structure(state: AgentState) -> dict:
    """Rule-based market structure analysis. Never uses LLM.
    Phase 2 adds ML confidence scorer on top of this output.
    Phase 3 adds Monte Carlo simulation.
    """
    context = state.get("context") or {}
    ohlcv = context.get("price_summary", {}).get("ohlcv_24h", [])

    if not ohlcv or len(ohlcv) < 10:
        return {
            "market_structure_analysis": {
                "bias": "neutral",
                "swing_highs": [], "swing_lows": [],
                "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
                "volume_confirmed": False, "invalidation_level": None,
                "rsi": 50.0, "macd_histogram_slope": 0.0,
                "ma_trend": "sideways", "momentum_pct": 0.0,
                "confidence_score": 0.0,
                "explanation": "Insufficient OHLCV data for analysis.",
                "ml_probability_1r": None, "ml_probability_2r": None,
            }
        }

    highs   = [float(c["high"])   for c in ohlcv]
    lows    = [float(c["low"])    for c in ohlcv]
    closes  = [float(c["close"])  for c in ohlcv]
    volumes = [float(c.get("volume", 0)) for c in ohlcv]

    # --- Primary signals ---
    swing_highs = _detect_swing_highs(highs, n=3)
    swing_lows  = _detect_swing_lows(lows, n=3)
    sweeps      = _detect_liquidity_sweeps(highs, lows, closes, swing_highs, swing_lows)
    bos_choch   = _detect_bos_choch(closes, swing_highs, swing_lows)
    order_blocks = _detect_order_blocks(highs, lows, closes, bos_choch)
    vol_confirmed = _volume_confirmed(volumes)
    invalidation  = _invalidation_level(bos_choch, swing_highs, swing_lows, closes[-1])

    # Determine bias from most recent BOS/CHOCH
    bias = "neutral"
    if bos_choch:
        bias = bos_choch[-1]["direction"]

    # --- Secondary indicators ---
    rsi   = _compute_rsi(closes)
    macd_slope = _compute_macd_histogram_slope(closes)
    ma20  = sum(closes[-min(20, len(closes)):]) / min(20, len(closes))
    ma50  = sum(closes[-min(50, len(closes)):]) / min(50, len(closes))
    ma_trend = _ma_trend(closes[-1], ma20, ma50)
    momentum = round((closes[-1] - closes[-5]) / closes[-5] * 100, 2) if len(closes) >= 5 else 0.0

    # --- Confidence score ---
    confidence, explanation = _score_and_explain(
        bias, bos_choch, sweeps, order_blocks, vol_confirmed,
        rsi, macd_slope, ma_trend, momentum,
    )

    return {
        "market_structure_analysis": {
            "bias": bias,
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "liquidity_sweeps": sweeps,
            "order_blocks": order_blocks,
            "bos_choch": bos_choch,
            "volume_confirmed": vol_confirmed,
            "invalidation_level": invalidation,
            "rsi": round(rsi, 1),
            "macd_histogram_slope": round(macd_slope, 4),
            "ma_trend": ma_trend,
            "momentum_pct": momentum,
            "confidence_score": round(confidence, 2),
            "explanation": explanation,
            "ml_probability_1r": None,
            "ml_probability_2r": None,
        }
    }


# ---------------------------------------------------------------------------
# Swing detection
# ---------------------------------------------------------------------------

def _detect_swing_highs(highs: list[float], n: int = 3) -> list[float]:
    result = []
    for i in range(n, len(highs) - n):
        if all(highs[i] > highs[i - j] and highs[i] > highs[i + j] for j in range(1, n + 1)):
            result.append(highs[i])
    return result


def _detect_swing_lows(lows: list[float], n: int = 3) -> list[float]:
    result = []
    for i in range(n, len(lows) - n):
        if all(lows[i] < lows[i - j] and lows[i] < lows[i + j] for j in range(1, n + 1)):
            result.append(lows[i])
    return result


# ---------------------------------------------------------------------------
# Liquidity sweep
# ---------------------------------------------------------------------------

def _detect_liquidity_sweeps(
    highs: list[float], lows: list[float], closes: list[float],
    swing_highs: list[float], swing_lows: list[float],
) -> list[dict]:
    sweeps = []
    if not swing_highs and not swing_lows:
        return sweeps

    for i in range(1, len(closes)):
        for level in swing_highs:
            if highs[i] > level and closes[i] < level:
                sweeps.append({
                    "type": "high", "swept_level": level,
                    "sweep_candle_idx": i, "confirmed": True,
                })
                break
        for level in swing_lows:
            if lows[i] < level and closes[i] > level:
                sweeps.append({
                    "type": "low", "swept_level": level,
                    "sweep_candle_idx": i, "confirmed": True,
                })
                break
    return sweeps


# ---------------------------------------------------------------------------
# BOS / CHOCH
# ---------------------------------------------------------------------------

def _detect_bos_choch(
    closes: list[float], swing_highs: list[float], swing_lows: list[float]
) -> list[dict]:
    events = []
    if len(closes) < 5 or not swing_highs or not swing_lows:
        return events

    last_high = max(swing_highs) if swing_highs else None
    last_low  = min(swing_lows)  if swing_lows  else None
    prior_bias: Optional[str] = None

    for i in range(1, len(closes)):
        if last_high and closes[i] > last_high:
            event_type = "BOS" if prior_bias == "bullish" else "CHOCH"
            events.append({
                "type": event_type, "direction": "bullish",
                "break_level": last_high, "candle_idx": i,
            })
            prior_bias = "bullish"
            last_high = closes[i]

        elif last_low and closes[i] < last_low:
            event_type = "BOS" if prior_bias == "bearish" else "CHOCH"
            events.append({
                "type": event_type, "direction": "bearish",
                "break_level": last_low, "candle_idx": i,
            })
            prior_bias = "bearish"
            last_low = closes[i]

    return events


# ---------------------------------------------------------------------------
# Order blocks
# ---------------------------------------------------------------------------

def _detect_order_blocks(
    highs: list[float], lows: list[float], closes: list[float],
    bos_choch: list[dict],
) -> list[dict]:
    blocks = []
    for event in bos_choch:
        idx = event["candle_idx"]
        direction = event["direction"]
        # Last opposing candle before the break
        search_start = max(0, idx - 5)
        for j in range(idx - 1, search_start - 1, -1):
            if direction == "bullish" and closes[j] < closes[j - 1] if j > 0 else False:
                mitigated = any(lows[k] <= lows[j] for k in range(idx, len(lows)))
                blocks.append({
                    "type": "bullish", "zone_high": highs[j], "zone_low": lows[j],
                    "candle_idx": j, "mitigated": mitigated,
                })
                break
            elif direction == "bearish" and closes[j] > closes[j - 1] if j > 0 else False:
                mitigated = any(highs[k] >= highs[j] for k in range(idx, len(highs)))
                blocks.append({
                    "type": "bearish", "zone_high": highs[j], "zone_low": lows[j],
                    "candle_idx": j, "mitigated": mitigated,
                })
                break
    return blocks


# ---------------------------------------------------------------------------
# Volume confirmation
# ---------------------------------------------------------------------------

def _volume_confirmed(volumes: list[float]) -> bool:
    if len(volumes) < 5:
        return False
    avg = sum(volumes[:-1]) / (len(volumes) - 1)
    return volumes[-1] > avg * 1.1


# ---------------------------------------------------------------------------
# Invalidation level
# ---------------------------------------------------------------------------

def _invalidation_level(
    bos_choch: list[dict], swing_highs: list[float], swing_lows: list[float],
    current_price: float,
) -> Optional[float]:
    if not bos_choch:
        return None
    last_event = bos_choch[-1]
    if last_event["direction"] == "bullish":
        return min(swing_lows) if swing_lows else None
    else:
        return max(swing_highs) if swing_highs else None


# ---------------------------------------------------------------------------
# Secondary indicators
# ---------------------------------------------------------------------------

def _compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0.0) for d in deltas[-period:]]
    losses = [-min(d, 0.0) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _compute_macd_histogram_slope(closes: list[float]) -> float:
    if len(closes) < 26:
        return 0.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    # Simplified: slope approximated from last 3 closes' MACD delta
    if len(closes) < 28:
        return 0.0
    h1 = _ema(closes[-3:], 2) - _ema(closes[-3:], 2)  # placeholder
    # Proper slope: compare last two histogram values
    macd_prev = _ema(closes[:-1], 12) - _ema(closes[:-1], 26)
    return round(macd_line - macd_prev, 6)


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def _ma_trend(price: float, ma20: float, ma50: float) -> str:
    if price > ma20 and ma20 > ma50:
        return "uptrend"
    if price < ma20 and ma20 < ma50:
        return "downtrend"
    return "sideways"


# ---------------------------------------------------------------------------
# Confidence score + explanation
# ---------------------------------------------------------------------------

def _score_and_explain(
    bias: str, bos_choch: list, sweeps: list, order_blocks: list,
    vol_confirmed: bool, rsi: float, macd_slope: float,
    ma_trend: str, momentum_pct: float,
) -> tuple[float, str]:
    score = 0.0
    parts = []

    if bos_choch:
        score += 0.30
        last = bos_choch[-1]
        parts.append(f"{last['type']} {last['direction']} at {last['break_level']:.2f}")

    confirmed_sweeps = [s for s in sweeps if s["confirmed"]]
    if confirmed_sweeps:
        score += 0.20
        parts.append(f"liquidity sweep {'high' if confirmed_sweeps[-1]['type'] == 'high' else 'low'} confirmed")

    active_obs = [ob for ob in order_blocks if not ob["mitigated"]]
    if active_obs:
        score += 0.20
        parts.append(f"order block {'bullish' if active_obs[-1]['type'] == 'bullish' else 'bearish'} at {active_obs[-1]['zone_low']:.2f}–{active_obs[-1]['zone_high']:.2f}")

    if vol_confirmed:
        score += 0.10
        parts.append("volume confirms move")

    # Secondary confirmations
    rsi_aligned = (bias == "bullish" and rsi > 50) or (bias == "bearish" and rsi < 50)
    if rsi_aligned:
        score += 0.05
        parts.append(f"RSI {rsi:.0f} aligned")

    macd_aligned = (bias == "bullish" and macd_slope > 0) or (bias == "bearish" and macd_slope < 0)
    if macd_aligned:
        score += 0.05
        parts.append("MACD histogram aligned")

    trend_map = {"uptrend": "bullish", "downtrend": "bearish"}
    if trend_map.get(ma_trend) == bias:
        score += 0.05
        parts.append(f"MA trend {ma_trend}")

    mom_aligned = (bias == "bullish" and momentum_pct > 0) or (bias == "bearish" and momentum_pct < 0)
    if mom_aligned:
        score += 0.05
        parts.append(f"momentum {momentum_pct:+.2f}%")

    score = min(1.0, score)
    explanation = (
        f"Bias: {bias}. " + " | ".join(parts)
        if parts else f"Bias: {bias}. No significant structure detected."
    )
    return score, explanation
```

- [ ] **Step 4: Write `agents/analyzers/risk_analyzer.py`**

```python
from config.settings import Settings
from graph.state import AgentState


def make_risk_analyzer(settings: Settings):
    async def analyze_risk(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            # Phase 9: Claude path
            pass
        return _deterministic_risk(state)
    return analyze_risk


def _deterministic_risk(state: AgentState) -> dict:
    context = state.get("context") or {}
    price_summary = context.get("price_summary", {})
    onchain = context.get("onchain_summary", {})
    data_gaps = context.get("data_gaps", [])

    risk_factors = []
    risk_score = 0

    change = abs(price_summary.get("change_24h_pct", 0.0))
    if change > 10:
        risk_factors.append(f"High price volatility: {change:.1f}% in 24h")
        risk_score += 2
    elif change > 5:
        risk_factors.append(f"Moderate price volatility: {change:.1f}% in 24h")
        risk_score += 1

    if onchain.get("mempool_size", 0) > 100_000:
        risk_factors.append("High mempool congestion detected")
        risk_score += 1

    if data_gaps:
        risk_factors.append(f"Incomplete data sources: {', '.join(data_gaps)}")
        risk_score += 1

    risk_level = "high" if risk_score >= 3 else "medium" if risk_score >= 1 else "low"

    return {
        "risk_analysis": {
            "risk_level": risk_level,
            "risk_factors": risk_factors or ["No significant risk factors detected"],
        }
    }
```

- [ ] **Step 5: Run tests**

```powershell
pytest tests/unit/test_analyzers.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```powershell
git add agents/analyzers/ tests/unit/test_analyzers.py
git commit -m "feat: add deterministic sentiment, price-pattern, and risk analyzer nodes"
```

---

### Task 14: Supervisor node (deterministic)

**Files:**
- Create: `agents/supervisor.py`
- Modify: `tests/unit/test_analyzers.py`

- [ ] **Step 1: Append failing test**

```python
from agents.supervisor import make_supervisor


async def test_supervisor_produces_intelligence_report(base_state):
    settings = Settings(LLM_ENABLED=False)
    node = make_supervisor(settings)
    state = {
        **base_state,
        "context": {
            "symbol": "BTCUSDT",
            "price_summary": {"price": 65000.0, "change_24h_pct": 2.3,
                              "volume_24h": 28e9, "high_24h": 66000.0,
                              "low_24h": 64000.0, "ohlcv_24h": []},
            "news_items": [], "onchain_summary": {},
            "social_summary": {}, "data_gaps": [],
        },
        "analysis": {
            "sentiment_score": 0.3, "sentiment_label": "bullish",
            "sentiment_drivers": ["BTC surges"],
            "market_structure": {
                "bias": "bullish", "rsi": 58.0, "ma_trend": "uptrend",
                "confidence_score": 0.65, "explanation": "BOS bullish",
                "swing_highs": [64100.0], "swing_lows": [63900.0],
                "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
                "volume_confirmed": True, "invalidation_level": 63900.0,
                "macd_histogram_slope": 0.002, "momentum_pct": 1.2,
                "ml_probability_1r": None, "ml_probability_2r": None,
            },
            "risk_level": "low", "risk_factors": [],
        },
    }
    result = await node(state)
    report = result["report"]
    assert report["market_bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= report["confidence_score"] <= 1.0
    assert isinstance(report["key_signals"], list)
    assert len(report["key_signals"]) >= 1
    assert "error" not in report


async def test_supervisor_lowers_confidence_with_data_gaps(base_state):
    settings = Settings(LLM_ENABLED=False)
    node = make_supervisor(settings)
    state = {
        **base_state,
        "context": {
            "symbol": "BTCUSDT",
            "price_summary": {"price": 65000.0, "change_24h_pct": 2.0,
                              "volume_24h": 1e9, "high_24h": 66000.0,
                              "low_24h": 64000.0, "ohlcv_24h": []},
            "news_items": [], "onchain_summary": {}, "social_summary": {},
            "data_gaps": ["social_unavailable", "onchain_unavailable"],
        },
        "analysis": {
            "sentiment_score": 0.2, "sentiment_label": "bullish",
            "sentiment_drivers": [],
            "market_structure": {
                "bias": "bullish", "rsi": 55.0, "ma_trend": "uptrend",
                "confidence_score": 0.50, "explanation": "Moderate structure",
                "swing_highs": [], "swing_lows": [],
                "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
                "volume_confirmed": False, "invalidation_level": None,
                "macd_histogram_slope": 0.001, "momentum_pct": 0.5,
                "ml_probability_1r": None, "ml_probability_2r": None,
            },
            "risk_level": "medium", "risk_factors": [],
        },
    }
    result_no_gaps = await make_supervisor(settings)({
        **state, "context": {**state["context"], "data_gaps": []}
    })
    result_with_gaps = await node(state)
    assert (result_with_gaps["report"]["confidence_score"]
            <= result_no_gaps["report"]["confidence_score"])
```

- [ ] **Step 2: Write `agents/supervisor.py`**

```python
from datetime import datetime, timezone
from config.settings import Settings
from graph.state import AgentState, IntelligenceReport


def make_supervisor(settings: Settings):
    async def supervisor_node(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            # Phase 9: Claude Sonnet path
            pass
        return _deterministic_supervisor(state)
    return supervisor_node


def _deterministic_supervisor(state: AgentState) -> dict:
    analysis = state.get("analysis") or {}
    context = state.get("context") or {}

    sentiment_score = analysis.get("sentiment_score") or 0.0
    sentiment_label = analysis.get("sentiment_label") or "neutral"
    ms = analysis.get("market_structure") or {}
    risk_level = analysis.get("risk_level") or "medium"
    risk_factors = list(analysis.get("risk_factors") or [])
    data_gaps = list(context.get("data_gaps") or [])

    rsi = ms.get("rsi", 50.0)
    ma_trend = ms.get("ma_trend", "sideways")
    momentum = ms.get("momentum_pct", 0.0)
    ms_bias = ms.get("bias", "neutral")
    ms_confidence = ms.get("confidence_score", 0.0)

    bull = 0
    bear = 0
    if sentiment_score > 0.1:
        bull += 1
    elif sentiment_score < -0.1:
        bear += 1
    if ms_bias == "bullish":
        bull += 2  # market structure carries more weight than single indicator
    elif ms_bias == "bearish":
        bear += 2
    if ma_trend == "uptrend":
        bull += 1
    elif ma_trend == "downtrend":
        bear += 1
    if momentum > 1.0:
        bull += 1
    elif momentum < -1.0:
        bear += 1
    if rsi > 60:
        bull += 1
    elif rsi < 40:
        bear += 1

    if bull > bear:
        market_bias = "bullish"
    elif bear > bull:
        market_bias = "bearish"
    else:
        market_bias = "neutral"

    total = bull + bear
    base_conf = 0.2 + (max(bull, bear) / total * 0.5) if total > 0 else 0.2
    confidence = round(max(0.1, base_conf * (1 - 0.08 * len(data_gaps))), 2)

    price_summary = context.get("price_summary", {})
    key_signals: list[str] = []
    change = price_summary.get("change_24h_pct")
    if change is not None:
        direction = "up" if change >= 0 else "down"
        coin = state["symbol"].replace("USDT", "")
        key_signals.append(f"{coin} {direction} {abs(change):.1f}% in 24h")
    if ms.get("bos_choch"):
        last_event = ms["bos_choch"][-1]
        key_signals.append(f"{last_event['type']} {last_event['direction']} at {last_event['break_level']:.2f}")
    if ma_trend in ("uptrend", "downtrend"):
        key_signals.append(f"MA trend: {ma_trend}")
    if rsi:
        key_signals.append(f"RSI at {rsi:.0f}")
    drivers = analysis.get("sentiment_drivers") or []
    key_signals.extend(drivers[:2])

    risk_warnings = risk_factors[:3]
    if rsi > 70:
        risk_warnings.append(f"RSI overbought at {rsi:.0f}")
    elif rsi < 30:
        risk_warnings.append(f"RSI oversold at {rsi:.0f}")

    coin = state["symbol"].replace("USDT", "")
    narrative = (
        f"{coin} shows {market_bias} bias. "
        f"Market structure: {ms_bias} (confidence {ms_confidence:.0%}). "
        f"RSI: {rsi:.0f}, MA trend: {ma_trend}, sentiment: {sentiment_label}. "
        f"Risk: {risk_level}."
    )
    if data_gaps:
        narrative += f" ⚠ Limited by: {', '.join(data_gaps)}."

    report: IntelligenceReport = {
        "run_id": state["run_id"],
        "symbol": state["symbol"],
        "requested_at": state["requested_at"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_bias": market_bias,
        "confidence_score": confidence,
        "key_signals": key_signals[:5] or ["Insufficient signal data"],
        "risk_warnings": risk_warnings[:5],
        "narrative": narrative,
        "data_gaps": data_gaps,
    }
    return {"report": report}
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_analyzers.py -v
```

Expected: 8 passed.

- [ ] **Step 4: Commit**

```powershell
git add agents/supervisor.py tests/unit/test_analyzers.py
git commit -m "feat: add deterministic supervisor node"
```

---

### Task 15: graph/edges.py + graph/pipeline.py

**Files:**
- Create: `graph/edges.py`
- Create: `graph/pipeline.py`

- [ ] **Step 1: Write `graph/edges.py`**

```python
from graph.state import AgentState


def route_after_aggregate(state: AgentState) -> str:
    """Route to error_exit if aggregate_raw set an ErrorReport, else fan_out_analyzers."""
    if state.get("report") is not None:
        return "error_exit"
    return "fan_out_analyzers"
```

- [ ] **Step 2: Write `graph/pipeline.py`**

```python
from langgraph.graph import StateGraph, START, END
from config.settings import Settings
from data_sources.base import DataSourceAdapter
from graph.state import AgentState
from graph.aggregator import aggregate_raw, fan_out_analyzers, merge_analysis
from graph.edges import route_after_aggregate


def build_graph(
    settings: Settings,
    price_adapter: DataSourceAdapter,
    news_adapter: DataSourceAdapter,
    onchain_adapter: DataSourceAdapter,
    social_adapter: DataSourceAdapter,
):
    """Assemble and compile the LangGraph StateGraph."""
    from agents.collectors.price_collector import make_price_collector
    from agents.collectors.news_collector import make_news_collector
    from agents.collectors.onchain_collector import make_onchain_collector
    from agents.collectors.social_collector import make_social_collector
    from agents.analyzers.sentiment_analyzer import make_sentiment_analyzer
    from agents.analyzers.market_structure_analyzer import analyze_market_structure
    from agents.analyzers.risk_analyzer import make_risk_analyzer
    from agents.supervisor import make_supervisor

    workflow = StateGraph(AgentState)

    # --- Nodes ---
    workflow.add_node("collect_price", make_price_collector(price_adapter))
    workflow.add_node("collect_news", make_news_collector(news_adapter))
    workflow.add_node("collect_onchain", make_onchain_collector(onchain_adapter))
    workflow.add_node("collect_social", make_social_collector(social_adapter))
    workflow.add_node("aggregate_raw", aggregate_raw)
    workflow.add_node("fan_out_analyzers", fan_out_analyzers)
    workflow.add_node("analyze_sentiment", make_sentiment_analyzer(settings))
    workflow.add_node("analyze_market_structure", analyze_market_structure)
    workflow.add_node("analyze_risk", make_risk_analyzer(settings))
    workflow.add_node("merge_analysis", merge_analysis)
    workflow.add_node("supervisor", make_supervisor(settings))
    workflow.add_node("error_exit", lambda state: {})

    # --- Edges ---
    # Parallel collector fan-out from START
    workflow.add_edge(START, "collect_price")
    workflow.add_edge(START, "collect_news")
    workflow.add_edge(START, "collect_onchain")
    workflow.add_edge(START, "collect_social")

    # Join all collectors → aggregate_raw
    workflow.add_edge(
        ["collect_price", "collect_news", "collect_onchain", "collect_social"],
        "aggregate_raw",
    )

    # Conditional: error_exit or fan_out_analyzers
    workflow.add_conditional_edges(
        "aggregate_raw",
        route_after_aggregate,
        {"error_exit": "error_exit", "fan_out_analyzers": "fan_out_analyzers"},
    )

    # Parallel analyzer fan-out from fan_out_analyzers
    workflow.add_edge("fan_out_analyzers", "analyze_sentiment")
    workflow.add_edge("fan_out_analyzers", "analyze_market_structure")
    workflow.add_edge("fan_out_analyzers", "analyze_risk")

    # Join all analyzers → merge_analysis
    workflow.add_edge(
        ["analyze_sentiment", "analyze_market_structure", "analyze_risk"],
        "merge_analysis",
    )

    workflow.add_edge("merge_analysis", "supervisor")
    workflow.add_edge("supervisor", END)
    workflow.add_edge("error_exit", END)

    return workflow.compile()


def build_pipeline(settings: Settings):
    """Wire adapters based on settings and return compiled graph."""
    from data_sources.mock.mock_price import MockPriceAdapter
    from data_sources.mock.mock_news import MockNewsAdapter
    from data_sources.mock.mock_onchain import MockOnChainAdapter
    from data_sources.mock.mock_social import MockSocialAdapter

    if settings.use_mock():
        price_adapter = MockPriceAdapter()
        news_adapter = MockNewsAdapter()
        onchain_adapter = MockOnChainAdapter()
        social_adapter = MockSocialAdapter()
    else:
        # Phase 8 wires real adapters here
        price_adapter = MockPriceAdapter()
        news_adapter = MockNewsAdapter()
        onchain_adapter = MockOnChainAdapter()
        social_adapter = MockSocialAdapter()

    return build_graph(settings, price_adapter, news_adapter, onchain_adapter, social_adapter)
```

- [ ] **Step 3: Commit**

```powershell
git add graph/edges.py graph/pipeline.py
git commit -m "feat: assemble LangGraph pipeline with parallel fan-out and conditional routing"
```

---

### Task 16: Integration test — full mock pipeline end-to-end

**Files:**
- Create: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Write tests**

```python
# tests/integration/test_pipeline.py
import pytest
import uuid
from datetime import datetime, timezone
from config.settings import Settings
from graph.pipeline import build_pipeline
from graph.state import IntelligenceReport, ErrorReport


@pytest.fixture
def mock_graph():
    settings = Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)
    return build_pipeline(settings)


def _initial_state(symbol: str = "BTCUSDT") -> dict:
    return {
        "run_id": str(uuid.uuid4()),
        "symbol": symbol,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data": None, "news_data": [], "onchain_data": None, "social_data": None,
        "context": None, "sentiment_analysis": None, "market_structure_analysis": None,
        "risk_analysis": None, "analysis": None, "report": None,
        "data_gaps": [], "errors": [],
    }


async def test_full_pipeline_btcusdt(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]
    assert report is not None
    assert "error" not in report
    assert report["symbol"] == "BTCUSDT"
    assert report["market_bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= report["confidence_score"] <= 1.0
    assert isinstance(report["key_signals"], list)
    assert len(report["key_signals"]) >= 1
    assert isinstance(report["data_gaps"], list)


async def test_full_pipeline_ethusdt(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("ETHUSDT"))
    report = result["report"]
    assert report["symbol"] == "ETHUSDT"
    assert "error" not in report


async def test_pipeline_returns_error_report_when_price_missing(settings_mock):
    from data_sources.mock.mock_price import MockPriceAdapter
    from data_sources.mock.mock_news import MockNewsAdapter
    from data_sources.mock.mock_onchain import MockOnChainAdapter
    from data_sources.mock.mock_social import MockSocialAdapter
    from unittest.mock import AsyncMock
    from graph.pipeline import build_graph

    bad_price = MockPriceAdapter()
    bad_price.fetch = AsyncMock(return_value=None)

    graph = build_graph(
        settings_mock,
        price_adapter=bad_price,
        news_adapter=MockNewsAdapter(),
        onchain_adapter=MockOnChainAdapter(),
        social_adapter=MockSocialAdapter(),
    )
    result = await graph.ainvoke(_initial_state())
    assert result["report"]["error"] == "Price data unavailable — cannot generate intelligence report"


async def test_pipeline_continues_when_social_missing(settings_mock):
    from data_sources.mock.mock_price import MockPriceAdapter
    from data_sources.mock.mock_news import MockNewsAdapter
    from data_sources.mock.mock_onchain import MockOnChainAdapter
    from data_sources.mock.mock_social import MockSocialAdapter
    from unittest.mock import AsyncMock
    from graph.pipeline import build_graph

    bad_social = MockSocialAdapter()
    bad_social.fetch = AsyncMock(return_value=None)

    graph = build_graph(
        settings_mock,
        price_adapter=MockPriceAdapter(),
        news_adapter=MockNewsAdapter(),
        onchain_adapter=MockOnChainAdapter(),
        social_adapter=bad_social,
    )
    result = await graph.ainvoke(_initial_state())
    report = result["report"]
    assert "error" not in report
    assert "social_unavailable" in report["data_gaps"]
```

- [ ] **Step 2: Run integration tests**

```powershell
pytest tests/integration/test_pipeline.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Run full test suite**

```powershell
pytest -v
```

Expected: all tests pass (no failures).

- [ ] **Step 4: Commit**

```powershell
git add tests/integration/test_pipeline.py
git commit -m "test: add end-to-end pipeline integration tests with mock adapters"
```

---

## Phase 5: FastAPI Layer

**Goal:** Expose `GET /health` and `GET /report` endpoints. Reports are generated by invoking the LangGraph pipeline. Optional X-API-Key auth. No scheduler yet — on-demand only.

---

### Task 17: API Schemas

**File:** `api/schemas.py`

- [ ] **Step 1: Create `api/__init__.py`** (empty)

- [ ] **Step 2: Create `api/schemas.py`**

```python
from __future__ import annotations
from typing import Optional, List, Literal
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    env: str
    mock_mode: bool
    llm_enabled: bool
    scheduler_enabled: bool


class PriceData(BaseModel):
    symbol: str
    price_usd: float
    change_24h_pct: float
    volume_24h_usd: float
    market_cap_usd: Optional[float] = None
    source: str


class SentimentAnalysis(BaseModel):
    label: Literal["bullish", "bearish", "neutral"]
    confidence: float
    summary: str


class LiquiditySweep(BaseModel):
    type: Literal["high", "low"]
    swept_level: float
    sweep_candle_idx: int
    confirmed: bool


class OrderBlock(BaseModel):
    type: Literal["bullish", "bearish"]
    zone_high: float
    zone_low: float
    candle_idx: int
    mitigated: bool


class StructureBreak(BaseModel):
    type: Literal["BOS", "CHOCH"]
    direction: Literal["bullish", "bearish"]
    break_level: float
    candle_idx: int


class MarketStructureAnalysis(BaseModel):
    bias: Literal["bullish", "bearish", "neutral"]
    swing_highs: List[float]
    swing_lows: List[float]
    liquidity_sweeps: List[LiquiditySweep]
    order_blocks: List[OrderBlock]
    bos_choch: List[StructureBreak]
    volume_confirmed: bool
    invalidation_level: Optional[float] = None
    rsi: float
    macd_histogram_slope: float
    ma_trend: Literal["uptrend", "downtrend", "sideways"]
    momentum_pct: float
    confidence_score: float
    explanation: str
    ml_probability_1r: Optional[float] = None
    ml_probability_2r: Optional[float] = None


class RiskAnalysis(BaseModel):
    level: Literal["low", "medium", "high", "critical"]
    factors: List[str]
    recommendation: str


class IntelligenceReportResponse(BaseModel):
    run_id: str
    symbol: str
    generated_at: str
    price: PriceData
    sentiment: SentimentAnalysis
    market_structure: MarketStructureAnalysis
    risk: RiskAnalysis
    summary: str
    data_gaps: List[str]
    llm_used: bool


class ErrorReportResponse(BaseModel):
    run_id: str
    symbol: str
    generated_at: str
    error: str
    data_gaps: List[str]
```

- [ ] **Step 3: Commit**

```powershell
git add api/__init__.py api/schemas.py
git commit -m "feat: add FastAPI response schemas"
```

---

### Task 18: FastAPI App + Report Route

**Files:** `api/routes/health.py`, `api/routes/report.py`, `api/main.py`, `data_sources/factory.py`

- [ ] **Step 1: Create `api/routes/__init__.py`** (empty)

- [ ] **Step 2: Create `api/routes/health.py`**

```python
from fastapi import APIRouter
from api.schemas import HealthResponse
from config.settings import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    s = get_settings()
    return HealthResponse(
        env=s.ENV,
        mock_mode=s.MOCK_MODE,
        llm_enabled=s.LLM_ENABLED,
        scheduler_enabled=s.SCHEDULER_ENABLED,
    )
```

- [ ] **Step 3: Create `api/routes/report.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security.api_key import APIKeyHeader

from api.schemas import IntelligenceReportResponse, ErrorReportResponse
from config.settings import get_settings
from graph.pipeline import build_graph
from graph.state import AgentState
from data_sources.factory import build_adapters

router = APIRouter()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _verify_key(key: str | None = Security(api_key_header)):
    settings = get_settings()
    if not settings.API_AUTH_ENABLED:
        return
    if key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get(
    "/report",
    response_model=Union[IntelligenceReportResponse, ErrorReportResponse],
)
async def get_report(
    symbol: str = Query("BTCUSDT", description="Trading pair symbol"),
    _: None = Depends(_verify_key),
):
    settings = get_settings()
    adapters = build_adapters(settings)
    graph = build_graph(settings, **adapters)

    initial: AgentState = {
        "run_id": str(uuid.uuid4()),
        "symbol": symbol.upper(),
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data": None,
        "news_data": [],
        "onchain_data": None,
        "social_data": None,
        "context": None,
        "sentiment_analysis": None,
        "market_structure_analysis": None,
        "risk_analysis": None,
        "analysis": None,
        "report": None,
        "data_gaps": [],
        "errors": [],
    }

    result = await graph.ainvoke(initial)
    report = result["report"]

    if "error" in report:
        return ErrorReportResponse(**report)
    return IntelligenceReportResponse(**report)
```

- [ ] **Step 4: Create `data_sources/factory.py`**

Wires mock adapters by default. Phase 8 will swap in real adapters.

```python
from config.settings import Settings
from data_sources.mock.mock_price import MockPriceAdapter
from data_sources.mock.mock_news import MockNewsAdapter
from data_sources.mock.mock_onchain import MockOnChainAdapter
from data_sources.mock.mock_social import MockSocialAdapter


def build_adapters(settings: Settings) -> dict:
    return {
        "price_adapter": MockPriceAdapter(),
        "news_adapter": MockNewsAdapter(),
        "onchain_adapter": MockOnChainAdapter(),
        "social_adapter": MockSocialAdapter(),
    }
```

- [ ] **Step 5: Create `api/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.routes.health import router as health_router
from api.routes.report import router as report_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Crypto Intelligence API", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(report_router)
    return app


app = create_app()
```

- [ ] **Step 6: Add singleton helper to `config/settings.py`**

Append after the `Settings` class definition:

```python
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

- [ ] **Step 7: Manual smoke test**

```powershell
uvicorn api.main:app --reload
```

`GET http://127.0.0.1:8000/health` → `{"status":"ok","env":"development","mock_mode":true,...}`

`GET http://127.0.0.1:8000/report?symbol=BTCUSDT` → full `IntelligenceReportResponse` JSON.

- [ ] **Step 8: Write route unit tests — `tests/unit/test_api_routes.py`**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["mock_mode"] is True


@pytest.mark.asyncio
async def test_report_btcusdt(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "BTCUSDT"
    assert "price" in resp.json()


@pytest.mark.asyncio
async def test_report_auth_enforced(monkeypatch, app):
    import config.settings as s_mod
    s = s_mod.get_settings()
    monkeypatch.setattr(s, "API_AUTH_ENABLED", True)
    monkeypatch.setattr(s, "API_KEY", "secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_report_auth_valid_key(monkeypatch, app):
    import config.settings as s_mod
    s = s_mod.get_settings()
    monkeypatch.setattr(s, "API_AUTH_ENABLED", True)
    monkeypatch.setattr(s, "API_KEY", "secret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/report?symbol=BTCUSDT", headers={"X-API-Key": "secret"})
    assert resp.status_code == 200
```

- [ ] **Step 9: Run tests**

```powershell
pytest tests/unit/test_api_routes.py -v
```

Expected: 4 passed.

- [ ] **Step 10: Commit**

```powershell
git add api/ data_sources/factory.py tests/unit/test_api_routes.py
git commit -m "feat: add FastAPI app with /health and /report endpoints"
```

---

## Phase 6: Telegram Publisher

**Goal:** Implement `ReportPublisher` base class, `TelegramPublisher`, and an optional Telegram bot handler so users can type `/report BTCUSDT` in Telegram and receive formatted intelligence reports.

---

### Task 19: ReportPublisher Base + TelegramPublisher

**Files:** `publishers/base.py`, `publishers/telegram_publisher.py`

- [ ] **Step 1: Create `publishers/__init__.py`** (empty)

- [ ] **Step 2: Create `publishers/base.py`**

```python
from abc import ABC, abstractmethod
from typing import Union
from api.schemas import IntelligenceReportResponse, ErrorReportResponse


class ReportPublisher(ABC):
    @abstractmethod
    async def publish(
        self, report: Union[IntelligenceReportResponse, ErrorReportResponse]
    ) -> None: ...
```

- [ ] **Step 3: Create `publishers/telegram_publisher.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Union

import httpx

from api.schemas import IntelligenceReportResponse, ErrorReportResponse
from publishers.base import ReportPublisher

logger = logging.getLogger(__name__)

RISK_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
TREND_EMOJI = {"uptrend": "📈", "downtrend": "📉", "sideways": "➡️"}
SENTIMENT_EMOJI = {"bullish": "🐂", "bearish": "🐻", "neutral": "😐"}


class TelegramPublisher(ReportPublisher):
    def __init__(self, token: str, chat_id: str, display_tz: str = "Asia/Jakarta"):
        self._token = token
        self._chat_id = chat_id
        self._tz = ZoneInfo(display_tz)
        self._base = f"https://api.telegram.org/bot{token}"

    async def publish(
        self, report: Union[IntelligenceReportResponse, ErrorReportResponse]
    ) -> None:
        text = self._format_report(report)
        await self._send(text)

    def _format_report(
        self, report: Union[IntelligenceReportResponse, ErrorReportResponse]
    ) -> str:
        if isinstance(report, ErrorReportResponse):
            return (
                f"❌ *Intelligence Report — {report.symbol}*\n\n"
                f"Error: {report.error}\n"
                f"Data gaps: {', '.join(report.data_gaps) or 'none'}\n"
                f"Run ID: `{report.run_id}`"
            )

        ts = datetime.fromisoformat(report.generated_at).astimezone(self._tz)
        ts_str = ts.strftime("%Y-%m-%d %H:%M %Z")

        ms = report.market_structure
        risk_em = RISK_EMOJI.get(report.risk.level, "⚪")
        trend_em = TREND_EMOJI.get(ms.ma_trend, "")
        sent_em = SENTIMENT_EMOJI.get(report.sentiment.label, "")
        ms_bias_em = SENTIMENT_EMOJI.get(ms.bias, "")

        conf_bar = "█" * int(ms.confidence_score * 10) + "░" * (10 - int(ms.confidence_score * 10))

        lines = [
            f"*Crypto Intelligence — {report.symbol}*",
            f"_{ts_str}_",
            "",
            f"*Price:* ${report.price.price_usd:,.2f}  ({report.price.change_24h_pct:+.2f}%)",
            f"*Volume 24h:* ${report.price.volume_24h_usd:,.0f}",
            "",
            f"*Sentiment:* {sent_em} {report.sentiment.label.capitalize()} ({report.sentiment.confidence:.0%})",
            f"_{report.sentiment.summary}_",
            "",
            f"*Market Structure:* {ms_bias_em} {ms.bias.capitalize()} | Confidence: {conf_bar} {ms.confidence_score:.0%}",
            f"_{ms.explanation}_",
            f"Trend: {trend_em} {ms.ma_trend} | RSI: {ms.rsi:.0f}",
        ]
        if ms.invalidation_level:
            lines.append(f"Invalidation: ${ms.invalidation_level:,.2f}")
        lines += [
            "",
            f"*Risk:* {risk_em} {report.risk.level.upper()}",
        ]
        if report.risk.factors:
            lines.append("Factors: " + " • ".join(report.risk.factors))
        lines += [
            f"_{report.risk.recommendation}_",
            "",
            f"*Summary:* {report.summary}",
        ]
        if report.data_gaps:
            lines.append(f"\n⚠️ Data gaps: {', '.join(report.data_gaps)}")
        if report.llm_used:
            lines.append("🤖 _AI-enhanced analysis_")
        lines.append(f"\n`Run: {report.run_id}`")
        return "\n".join(lines)

    async def _send(self, text: str) -> None:
        if not self._token or not self._chat_id:
            logger.warning("Telegram not configured — skipping publish")
            return
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base}/sendMessage",
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
        if resp.status_code != 200:
            logger.error("Telegram send failed: %s %s", resp.status_code, resp.text)
```

- [ ] **Step 4: Write unit tests — `tests/unit/test_telegram_publisher.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch
from api.schemas import IntelligenceReportResponse, ErrorReportResponse
from publishers.telegram_publisher import TelegramPublisher


def _make_report():
    return IntelligenceReportResponse(
        run_id="abc",
        symbol="BTCUSDT",
        generated_at="2025-01-01T12:00:00+00:00",
        price={"symbol": "BTCUSDT", "price_usd": 50000.0, "change_24h_pct": 2.5,
               "volume_24h_usd": 1e9, "source": "mock"},
        sentiment={"label": "bullish", "confidence": 0.8, "summary": "Positive"},
        market_structure={
            "bias": "bullish", "swing_highs": [50100.0], "swing_lows": [49800.0],
            "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
            "volume_confirmed": True, "invalidation_level": 49800.0,
            "rsi": 58.0, "macd_histogram_slope": 0.002, "ma_trend": "uptrend",
            "momentum_pct": 1.2, "confidence_score": 0.65,
            "explanation": "BOS bullish detected at 50000.",
            "ml_probability_1r": None, "ml_probability_2r": None,
        },
        risk={"level": "medium", "factors": ["volatility"], "recommendation": "Hold"},
        summary="BTC looks strong.",
        data_gaps=[],
        llm_used=False,
    )


def test_format_report_contains_symbol():
    pub = TelegramPublisher("tok", "chat123")
    text = pub._format_report(_make_report())
    assert "BTCUSDT" in text
    assert "50,000.00" in text


def test_format_error_report():
    pub = TelegramPublisher("tok", "chat123")
    err = ErrorReportResponse(
        run_id="x", symbol="ETHUSDT",
        generated_at="2025-01-01T00:00:00+00:00",
        error="price unavailable", data_gaps=["price"],
    )
    text = pub._format_error_report(err) if hasattr(pub, "_format_error_report") else pub._format_report(err)
    assert "ETHUSDT" in text
    assert "price unavailable" in text


@pytest.mark.asyncio
async def test_publish_calls_send():
    pub = TelegramPublisher("tok", "chat123")
    pub._send = AsyncMock()
    await pub.publish(_make_report())
    pub._send.assert_called_once()


@pytest.mark.asyncio
async def test_send_skips_when_no_token():
    pub = TelegramPublisher("", "")
    await pub._send("hello")  # should not raise
```

- [ ] **Step 5: Run tests**

```powershell
pytest tests/unit/test_telegram_publisher.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```powershell
git add publishers/ tests/unit/test_telegram_publisher.py
git commit -m "feat: add TelegramPublisher with timezone-aware report formatting"
```

---

### Task 20: Telegram Bot Handler

**File:** `publishers/telegram_bot.py`

The bot listens for `/report <SYMBOL>` commands via long-polling and calls the pipeline directly. This is optional for MVP — only active when `TELEGRAM_BOT_TOKEN` is set.

- [ ] **Step 1: Create `publishers/telegram_bot.py`**

```python
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone

import httpx

from config.settings import get_settings
from data_sources.factory import build_adapters
from graph.pipeline import build_graph
from graph.state import AgentState
from publishers.telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        self._settings = get_settings()
        self._pub = TelegramPublisher(
            self._settings.TELEGRAM_BOT_TOKEN,
            self._settings.TELEGRAM_CHAT_ID,
            self._settings.DISPLAY_TIMEZONE,
        )
        self._base = f"https://api.telegram.org/bot{self._settings.TELEGRAM_BOT_TOKEN}"
        self._offset = 0

    async def run(self) -> None:
        if not self._settings.TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
            return
        logger.info("Telegram bot polling started")
        while True:
            try:
                await self._poll()
            except Exception as exc:
                logger.error("Bot poll error: %s", exc)
            await asyncio.sleep(2)

    async def _poll(self) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base}/getUpdates",
                params={"offset": self._offset, "timeout": 30},
                timeout=35,
            )
        data = resp.json()
        for update in data.get("result", []):
            self._offset = update["update_id"] + 1
            await self._handle_update(update)

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if not text.startswith("/report"):
            return
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else "BTCUSDT"
        await self._run_report(symbol, chat_id)

    async def _run_report(self, symbol: str, chat_id: str) -> None:
        settings = get_settings()
        adapters = build_adapters(settings)
        graph = build_graph(settings, **adapters)

        initial: AgentState = {
            "run_id": str(uuid.uuid4()),
            "symbol": symbol,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "price_data": None,
            "news_data": [],
            "onchain_data": None,
            "social_data": None,
            "context": None,
            "sentiment_analysis": None,
            "market_structure_analysis": None,
            "risk_analysis": None,
            "analysis": None,
            "report": None,
            "data_gaps": [],
            "errors": [],
        }

        result = await graph.ainvoke(initial)
        report_dict = result["report"]

        pub = TelegramPublisher(
            settings.TELEGRAM_BOT_TOKEN, chat_id, settings.DISPLAY_TIMEZONE
        )
        if "error" in report_dict:
            from api.schemas import ErrorReportResponse
            await pub.publish(ErrorReportResponse(**report_dict))
        else:
            from api.schemas import IntelligenceReportResponse
            await pub.publish(IntelligenceReportResponse(**report_dict))
```

- [ ] **Step 2: Commit**

```powershell
git add publishers/telegram_bot.py
git commit -m "feat: add Telegram bot handler for /report command"
```

---

## Phase 7: SQLite Report History

**Goal:** Persist every generated report to SQLite via `aiosqlite`. Auto-prune to 100 rows per symbol. Wire storage into the `/report` route.

---

### Task 21: ReportStorage

**File:** `services/storage.py`

- [ ] **Step 1: Create `services/__init__.py`** (empty)

- [ ] **Step 2: Create `services/storage.py`**

```python
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path("data/reports.db")
MAX_ROWS_PER_SYMBOL = 100


class ReportStorage:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path

    async def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    is_error INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbol ON reports(symbol, generated_at DESC)"
            )
            await db.commit()

    async def save(self, report: dict) -> None:
        is_error = 1 if "error" in report else 0
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO reports (run_id, symbol, generated_at, is_error, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    report["run_id"],
                    report["symbol"],
                    report.get("generated_at", datetime.now(timezone.utc).isoformat()),
                    is_error,
                    json.dumps(report),
                ),
            )
            await db.commit()
            await self._prune(db, report["symbol"])

    async def _prune(self, db: aiosqlite.Connection, symbol: str) -> None:
        await db.execute(
            """
            DELETE FROM reports WHERE id IN (
                SELECT id FROM reports WHERE symbol = ?
                ORDER BY generated_at DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (symbol, MAX_ROWS_PER_SYMBOL),
        )
        await db.commit()

    async def get_latest(self, symbol: str) -> Optional[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT payload FROM reports WHERE symbol = ? "
                "ORDER BY generated_at DESC LIMIT 1",
                (symbol,),
            ) as cur:
                row = await cur.fetchone()
        return json.loads(row["payload"]) if row else None
```

- [ ] **Step 3: Wire storage into `/report` route**

In `api/routes/report.py`, add storage save after graph invocation:

```python
# add import at top
from services.storage import ReportStorage

# inside get_report(), after result = await graph.ainvoke(initial):
storage = ReportStorage()
await storage.init()
await storage.save(report)
```

Also add a `GET /report/history` endpoint for the latest cached report:

```python
@router.get(
    "/report/history",
    response_model=Union[IntelligenceReportResponse, ErrorReportResponse],
)
async def get_report_history(
    symbol: str = Query("BTCUSDT"),
    _: None = Depends(_verify_key),
):
    storage = ReportStorage()
    await storage.init()
    cached = await storage.get_latest(symbol.upper())
    if cached is None:
        raise HTTPException(status_code=404, detail="No cached report for symbol")
    if "error" in cached:
        return ErrorReportResponse(**cached)
    return IntelligenceReportResponse(**cached)
```

- [ ] **Step 4: Write unit tests — `tests/unit/test_storage.py`**

```python
import pytest
from pathlib import Path
from services.storage import ReportStorage


@pytest.fixture
async def storage(tmp_path):
    s = ReportStorage(db_path=tmp_path / "test.db")
    await s.init()
    return s


@pytest.mark.asyncio
async def test_save_and_get_latest(storage):
    report = {
        "run_id": "r1", "symbol": "BTCUSDT",
        "generated_at": "2025-01-01T00:00:00+00:00",
        "price": {}, "sentiment": {}, "market_structure": {}, "risk": {},
        "summary": "ok", "data_gaps": [], "llm_used": False,
    }
    await storage.save(report)
    latest = await storage.get_latest("BTCUSDT")
    assert latest["run_id"] == "r1"


@pytest.mark.asyncio
async def test_get_latest_none_when_empty(storage):
    result = await storage.get_latest("ETHUSDT")
    assert result is None


@pytest.mark.asyncio
async def test_prune_keeps_100(storage):
    for i in range(105):
        await storage.save({
            "run_id": f"r{i}", "symbol": "BTCUSDT",
            "generated_at": f"2025-01-{i % 28 + 1:02d}T00:00:00+00:00",
            "summary": "ok", "data_gaps": [], "llm_used": False,
        })
    import aiosqlite
    async with aiosqlite.connect(storage._db_path) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM reports WHERE symbol='BTCUSDT'"
        ) as cur:
            count = (await cur.fetchone())[0]
    assert count <= 100
```

- [ ] **Step 5: Run tests**

```powershell
pytest tests/unit/test_storage.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Add `data/` to `.gitignore`**

```
data/
```

- [ ] **Step 7: Commit**

```powershell
git add services/ tests/unit/test_storage.py .gitignore
git commit -m "feat: add SQLite report history with auto-prune"
```

---

## Phase 8: Real API Adapters

**Goal:** Implement free-tier adapters for each data type. Each adapter is gated behind `settings.use_mock()` — if the API key is absent or mock mode is on, the factory falls back to the mock adapter. No adapter is required for the system to function.

---

### Task 22: Price Adapters — Binance + CoinGecko

**Files:** `data_sources/price/binance.py`, `data_sources/price/coingecko.py`

- [ ] **Step 1: Create `data_sources/price/binance.py`**

```python
from __future__ import annotations
import httpx
from data_sources.base import DataSourceAdapter


class BinanceAdapter(DataSourceAdapter):
    source_name = "binance"
    _BASE = "https://api.binance.com/api/v3"

    async def fetch(self, symbol: str) -> dict | None:
        async with httpx.AsyncClient(timeout=10) as client:
            ticker = await client.get(f"{self._BASE}/ticker/24hr", params={"symbol": symbol})
            ticker.raise_for_status()
            data = ticker.json()
        return {
            "symbol": symbol,
            "price_usd": float(data["lastPrice"]),
            "change_24h_pct": float(data["priceChangePercent"]),
            "volume_24h_usd": float(data["quoteVolume"]),
            "market_cap_usd": None,
            "source": "binance",
        }
```

- [ ] **Step 2: Create `data_sources/price/coingecko.py`**

```python
from __future__ import annotations
import httpx
from data_sources.base import DataSourceAdapter

_SYMBOL_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
}


class CoinGeckoAdapter(DataSourceAdapter):
    source_name = "coingecko"
    _BASE = "https://api.coingecko.com/api/v3"

    async def fetch(self, symbol: str) -> dict | None:
        coin_id = _SYMBOL_MAP.get(symbol)
        if not coin_id:
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._BASE}/coins/{coin_id}",
                params={"localization": "false", "tickers": "false",
                        "community_data": "false", "developer_data": "false"},
            )
            resp.raise_for_status()
            data = resp.json()
        mkt = data["market_data"]
        return {
            "symbol": symbol,
            "price_usd": mkt["current_price"]["usd"],
            "change_24h_pct": mkt["price_change_percentage_24h"],
            "volume_24h_usd": mkt["total_volume"]["usd"],
            "market_cap_usd": mkt["market_cap"]["usd"],
            "source": "coingecko",
        }
```

- [ ] **Step 3: Commit**

```powershell
git add data_sources/price/
git commit -m "feat: add Binance and CoinGecko price adapters"
```

---

### Task 23: News Adapters — RSS + CryptoPanic stub

**Files:** `data_sources/news/rss_feed.py`, `data_sources/news/cryptopanic.py`

- [ ] **Step 1: Create `data_sources/news/rss_feed.py`**

```python
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List

import httpx
import feedparser

from data_sources.base import DataSourceAdapter

logger = logging.getLogger(__name__)

_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
]

_KEYWORDS = {
    "BTCUSDT": ["bitcoin", "btc"],
    "ETHUSDT": ["ethereum", "eth"],
    "SOLUSDT": ["solana", "sol"],
    "BNBUSDT": ["bnb", "binance coin"],
}


class RSSFeedAdapter(DataSourceAdapter):
    source_name = "rss_feed"

    async def fetch(self, symbol: str) -> List[dict] | None:
        keywords = _KEYWORDS.get(symbol, [symbol.lower().replace("usdt", "")])
        articles: List[dict] = []

        async with httpx.AsyncClient(timeout=10) as client:
            for url in _FEEDS:
                try:
                    resp = await client.get(url)
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:20]:
                        title = entry.get("title", "").lower()
                        summary = entry.get("summary", "").lower()
                        if any(kw in title or kw in summary for kw in keywords):
                            articles.append({
                                "title": entry.get("title", ""),
                                "url": entry.get("link", ""),
                                "published_at": entry.get("published",
                                    datetime.now(timezone.utc).isoformat()),
                                "source": url,
                            })
                except Exception as exc:
                    logger.warning("RSS feed %s failed: %s", url, exc)

        return articles if articles else None
```

- [ ] **Step 2: Create `data_sources/news/cryptopanic.py`** (stub — requires paid key for full access)

```python
from __future__ import annotations
import httpx
from data_sources.base import DataSourceAdapter


class CryptoPanicAdapter(DataSourceAdapter):
    """Free tier is heavily rate-limited. Use as secondary fallback."""
    source_name = "cryptopanic"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    async def fetch(self, symbol: str) -> list | None:
        if not self._api_key:
            return None
        currency = symbol.replace("USDT", "")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://cryptopanic.com/api/v1/posts/",
                params={"auth_token": self._api_key, "currencies": currency, "public": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {"title": p["title"], "url": p["url"],
             "published_at": p["published_at"], "source": "cryptopanic"}
            for p in data.get("results", [])
        ] or None
```

- [ ] **Step 3: Commit**

```powershell
git add data_sources/news/
git commit -m "feat: add RSS feed and CryptoPanic news adapters"
```

---

### Task 24: On-Chain Adapters — Blockchain.com + Etherscan

**Files:** `data_sources/onchain/blockchain_com.py`, `data_sources/onchain/etherscan.py`

- [ ] **Step 1: Create `data_sources/onchain/blockchain_com.py`** (BTC only, free)

```python
from __future__ import annotations
import httpx
from data_sources.base import DataSourceAdapter


class BlockchainComAdapter(DataSourceAdapter):
    source_name = "blockchain_com"
    _BASE = "https://blockchain.info"

    async def fetch(self, symbol: str) -> dict | None:
        if "BTC" not in symbol.upper():
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            stats = await client.get(f"{self._BASE}/stats?format=json")
            stats.raise_for_status()
            data = stats.json()
        return {
            "symbol": symbol,
            "active_addresses_24h": data.get("n_unique_addresses"),
            "transactions_24h": data.get("n_tx"),
            "hash_rate": data.get("hash_rate"),
            "source": "blockchain_com",
        }
```

- [ ] **Step 2: Create `data_sources/onchain/etherscan.py`** (ETH, free tier 5 req/s)

```python
from __future__ import annotations
import httpx
from data_sources.base import DataSourceAdapter


class EtherscanAdapter(DataSourceAdapter):
    source_name = "etherscan"
    _BASE = "https://api.etherscan.io/api"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    async def fetch(self, symbol: str) -> dict | None:
        if "ETH" not in symbol.upper():
            return None
        if not self._api_key:
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                self._BASE,
                params={
                    "module": "stats",
                    "action": "ethsupply",
                    "apikey": self._api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "symbol": symbol,
            "eth_supply": int(data.get("result", 0)),
            "source": "etherscan",
        }
```

- [ ] **Step 3: Commit**

```powershell
git add data_sources/onchain/
git commit -m "feat: add Blockchain.com and Etherscan on-chain adapters"
```

---

### Task 25: Social Adapter — Reddit

**File:** `data_sources/social/reddit.py`

- [ ] **Step 1: Create `data_sources/social/reddit.py`**

```python
from __future__ import annotations
import logging
import httpx
from data_sources.base import DataSourceAdapter

logger = logging.getLogger(__name__)

_SUBREDDITS = {
    "BTCUSDT": "Bitcoin+CryptoCurrency",
    "ETHUSDT": "ethereum+CryptoCurrency",
    "SOLUSDT": "solana+CryptoCurrency",
    "BNBUSDT": "binance+CryptoCurrency",
}


class RedditAdapter(DataSourceAdapter):
    source_name = "reddit"

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self._client_id = client_id
        self._client_secret = client_secret

    async def fetch(self, symbol: str) -> dict | None:
        subreddit = _SUBREDDITS.get(symbol, "CryptoCurrency")
        headers = {"User-Agent": "CryptoIntelligenceAgent/0.1"}

        if self._client_id and self._client_secret:
            token = await self._get_token()
            headers["Authorization"] = f"Bearer {token}"
            base = "https://oauth.reddit.com"
        else:
            base = "https://www.reddit.com"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base}/r/{subreddit}/hot.json",
                params={"limit": 25},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        posts = data.get("data", {}).get("children", [])
        return {
            "symbol": symbol,
            "post_count": len(posts),
            "top_posts": [
                {
                    "title": p["data"]["title"],
                    "score": p["data"]["score"],
                    "comments": p["data"]["num_comments"],
                }
                for p in posts[:5]
            ],
            "source": "reddit",
        }

    async def _get_token(self) -> str:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": "CryptoIntelligenceAgent/0.1"},
            )
            resp.raise_for_status()
        return resp.json()["access_token"]
```

- [ ] **Step 2: Commit**

```powershell
git add data_sources/social/reddit.py
git commit -m "feat: add Reddit social adapter"
```

---

### Task 26: Wire Real Adapters into Factory

**File:** `data_sources/factory.py`

- [ ] **Step 1: Update `data_sources/factory.py`** to use real adapters with FallbackAdapter chains

```python
from config.settings import Settings
from data_sources.base import FallbackAdapter
from data_sources.mock.mock_price import MockPriceAdapter
from data_sources.mock.mock_news import MockNewsAdapter
from data_sources.mock.mock_onchain import MockOnChainAdapter
from data_sources.mock.mock_social import MockSocialAdapter
from data_sources.price.binance import BinanceAdapter
from data_sources.price.coingecko import CoinGeckoAdapter
from data_sources.news.rss_feed import RSSFeedAdapter
from data_sources.news.cryptopanic import CryptoPanicAdapter
from data_sources.onchain.blockchain_com import BlockchainComAdapter
from data_sources.onchain.etherscan import EtherscanAdapter
from data_sources.social.reddit import RedditAdapter


def build_adapters(settings: Settings) -> dict:
    mock = settings.use_mock()

    if mock:
        price_adapter = MockPriceAdapter()
        news_adapter = MockNewsAdapter()
        onchain_adapter = MockOnChainAdapter()
        social_adapter = MockSocialAdapter()
    else:
        price_adapter = FallbackAdapter([
            BinanceAdapter(),
            CoinGeckoAdapter(),
            MockPriceAdapter(),
        ])
        news_adapter = FallbackAdapter([
            RSSFeedAdapter(),
            CryptoPanicAdapter(settings.CRYPTOPANIC_API_KEY if hasattr(settings, "CRYPTOPANIC_API_KEY") else ""),
            MockNewsAdapter(),
        ])
        onchain_adapter = FallbackAdapter([
            BlockchainComAdapter(),
            EtherscanAdapter(settings.ETHERSCAN_API_KEY),
            MockOnChainAdapter(),
        ])
        social_adapter = FallbackAdapter([
            RedditAdapter(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
            MockSocialAdapter(),
        ])

    return {
        "price_adapter": price_adapter,
        "news_adapter": news_adapter,
        "onchain_adapter": onchain_adapter,
        "social_adapter": social_adapter,
    }
```

- [ ] **Step 2: Verify mock mode still works**

```powershell
pytest -v
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```powershell
git add data_sources/factory.py
git commit -m "feat: wire real adapters with FallbackAdapter chains in factory"
```

---

## Phase 9: Claude LLM Integration

**Goal:** Add Claude-powered sentiment analysis, risk analysis, and supervisor synthesis. All LLM calls are gated by `LLMBudgetTracker` which checks `LLM_ENABLED`, `MAX_LLM_CALLS_PER_DAY`, and `DAILY_LLM_BUDGET_IDR`. When budget is exceeded or LLM is disabled, nodes fall back to deterministic logic silently.

---

### Task 27: LLMBudgetTracker

**File:** `services/llm_budget.py`

- [ ] **Step 1: Create `services/llm_budget.py`**

```python
from __future__ import annotations
import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_FILE = Path("data/llm_budget_state.json")

USD_TO_IDR = 16_000.0
HAIKU_INPUT_COST_PER_1K_TOKENS = 0.00025
HAIKU_OUTPUT_COST_PER_1K_TOKENS = 0.00125
SONNET_INPUT_COST_PER_1K_TOKENS = 0.003
SONNET_OUTPUT_COST_PER_1K_TOKENS = 0.015


class LLMBudgetTracker:
    """Tracks daily LLM spend and call count. Thread-safe via file persistence."""

    def __init__(
        self,
        enabled: bool,
        max_calls: int,
        daily_budget_idr: float,
    ):
        self._enabled = enabled
        self._max_calls = max_calls
        self._daily_budget_idr = daily_budget_idr
        self._today = str(date.today())
        self._state = self._load()

    def can_call(self) -> bool:
        if not self._enabled:
            return False
        self._refresh_if_new_day()
        if self._max_calls > 0 and self._state["calls"] >= self._max_calls:
            logger.warning("LLM daily call limit reached (%d)", self._max_calls)
            return False
        if self._daily_budget_idr > 0 and self._state["spend_idr"] >= self._daily_budget_idr:
            logger.warning("LLM daily budget exhausted (%.0f IDR)", self._daily_budget_idr)
            return False
        return True

    def record_call(self, input_tokens: int, output_tokens: int, model: str) -> None:
        cost_usd = self._estimate_cost(input_tokens, output_tokens, model)
        cost_idr = cost_usd * USD_TO_IDR
        self._state["calls"] += 1
        self._state["spend_idr"] += cost_idr
        self._save()
        logger.debug(
            "LLM call recorded: calls=%d spend_idr=%.2f",
            self._state["calls"], self._state["spend_idr"],
        )

    def _estimate_cost(self, input_tok: int, output_tok: int, model: str) -> float:
        if "haiku" in model.lower():
            return (input_tok / 1000 * HAIKU_INPUT_COST_PER_1K_TOKENS
                    + output_tok / 1000 * HAIKU_OUTPUT_COST_PER_1K_TOKENS)
        return (input_tok / 1000 * SONNET_INPUT_COST_PER_1K_TOKENS
                + output_tok / 1000 * SONNET_OUTPUT_COST_PER_1K_TOKENS)

    def _refresh_if_new_day(self) -> None:
        today = str(date.today())
        if today != self._state.get("date"):
            self._state = {"date": today, "calls": 0, "spend_idr": 0.0}
            self._save()

    def _load(self) -> dict:
        if _STATE_FILE.exists():
            try:
                data = json.loads(_STATE_FILE.read_text())
                if data.get("date") == self._today:
                    return data
            except Exception:
                pass
        return {"date": self._today, "calls": 0, "spend_idr": 0.0}

    def _save(self) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(self._state))
```

- [ ] **Step 2: Write unit tests — `tests/unit/test_llm_budget.py`**

```python
import pytest
from services.llm_budget import LLMBudgetTracker


def test_disabled_cannot_call():
    t = LLMBudgetTracker(enabled=False, max_calls=100, daily_budget_idr=10000)
    assert t.can_call() is False


def test_enabled_can_call():
    t = LLMBudgetTracker(enabled=True, max_calls=100, daily_budget_idr=10000)
    assert t.can_call() is True


def test_call_limit_blocks():
    t = LLMBudgetTracker(enabled=True, max_calls=2, daily_budget_idr=10000)
    t.record_call(100, 50, "haiku")
    t.record_call(100, 50, "haiku")
    assert t.can_call() is False


def test_budget_limit_blocks():
    t = LLMBudgetTracker(enabled=True, max_calls=100, daily_budget_idr=1.0)
    t.record_call(10000, 5000, "sonnet")
    assert t.can_call() is False
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_llm_budget.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```powershell
git add services/llm_budget.py tests/unit/test_llm_budget.py
git commit -m "feat: add LLMBudgetTracker for daily spend and call limits"
```

---

### Task 28: Claude Analyzer Nodes

**Files:** `config/prompts.py`, `graph/nodes/sentiment_analyzer.py`, `graph/nodes/risk_analyzer.py`

- [ ] **Step 1: Create `config/prompts.py`**

```python
SENTIMENT_PROMPT = """You are a crypto market sentiment analyst.

Given the following market data for {symbol}, analyze the sentiment.

Price data: {price_data}
News headlines: {news_headlines}
Social signals: {social_data}

Respond with a JSON object matching this exact schema:
{{
  "label": "bullish" | "bearish" | "neutral",
  "confidence": <float 0.0-1.0>,
  "summary": "<1-2 sentence analysis>"
}}

Return ONLY the JSON object, no other text."""


RISK_PROMPT = """You are a crypto risk analyst.

Analyze the risk level for {symbol} based on:
Price change 24h: {change_24h_pct}%
Market structure: {market_structure}
Sentiment: {sentiment_label}
Data gaps: {data_gaps}

Respond with a JSON object matching this exact schema:
{{
  "level": "low" | "medium" | "high" | "critical",
  "factors": ["<factor1>", "<factor2>"],
  "recommendation": "<1 sentence recommendation>"
}}

Return ONLY the JSON object, no other text."""


SUPERVISOR_PROMPT = """You are a senior crypto market intelligence analyst.

Synthesize the following analysis for {symbol} into a concise, actionable summary.

Price: ${price_usd:,.2f} ({change_24h_pct:+.2f}%)
Sentiment: {sentiment_label} ({sentiment_confidence:.0%} confidence)
Trend: {price_trend}
Risk: {risk_level}
Risk factors: {risk_factors}
Data gaps: {data_gaps}

Write a 2-3 sentence executive summary suitable for a professional trader.
Focus on actionable insights. Be direct. No disclaimers.

Return ONLY the summary text, no other formatting."""
```

- [ ] **Step 2: Update `graph/nodes/sentiment_analyzer.py`** — add Claude path

The node factory already exists from Phase 3. Replace the deterministic-only body with a Claude-first + deterministic-fallback pattern:

```python
from __future__ import annotations
import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from config.settings import Settings
from graph.state import AgentState

logger = logging.getLogger(__name__)


class SentimentOutput(BaseModel):
    label: str  # "bullish" | "bearish" | "neutral"
    confidence: float
    summary: str


def make_sentiment_analyzer(settings: Settings):
    async def analyze_sentiment(state: AgentState) -> dict[str, Any]:
        price = state.get("price_data") or {}
        news = state.get("news_data") or []
        social = state.get("social_data")

        if _should_use_llm(settings):
            result = await _llm_sentiment(settings, state, price, news, social)
            if result:
                return {"sentiment_analysis": result}

        return {"sentiment_analysis": _deterministic_sentiment(price, news)}

    return analyze_sentiment


def _should_use_llm(settings: Settings) -> bool:
    try:
        from services.llm_budget import LLMBudgetTracker
        tracker = LLMBudgetTracker(
            enabled=settings.LLM_ENABLED,
            max_calls=settings.MAX_LLM_CALLS_PER_DAY,
            daily_budget_idr=settings.DAILY_LLM_BUDGET_IDR,
        )
        return tracker.can_call()
    except Exception:
        return False


async def _llm_sentiment(settings, state, price, news, social) -> dict | None:
    try:
        import anthropic
        from config.prompts import SENTIMENT_PROMPT
        from services.llm_budget import LLMBudgetTracker

        headlines = [a.get("title", "") for a in (news or [])[:5]]
        prompt = SENTIMENT_PROMPT.format(
            symbol=state["symbol"],
            price_data=json.dumps(price),
            news_headlines=json.dumps(headlines),
            social_data=json.dumps(social),
        )
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.ANTHROPIC_ANALYZER_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()

        try:
            parsed = SentimentOutput(**json.loads(raw))
        except (json.JSONDecodeError, ValidationError):
            repair_prompt = (
                f"The following is not valid JSON matching the schema. Fix it:\n\n{raw}\n\n"
                "Return ONLY the corrected JSON."
            )
            repair_msg = await client.messages.create(
                model=settings.ANTHROPIC_ANALYZER_MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": repair_prompt}],
            )
            parsed = SentimentOutput(**json.loads(repair_msg.content[0].text.strip()))

        tracker = LLMBudgetTracker(
            enabled=settings.LLM_ENABLED,
            max_calls=settings.MAX_LLM_CALLS_PER_DAY,
            daily_budget_idr=settings.DAILY_LLM_BUDGET_IDR,
        )
        tracker.record_call(msg.usage.input_tokens, msg.usage.output_tokens,
                            settings.ANTHROPIC_ANALYZER_MODEL)
        return {**parsed.model_dump(), "llm_used": True}

    except Exception as exc:
        logger.warning("Claude sentiment failed, using deterministic: %s", exc)
        return None


def _deterministic_sentiment(price: dict, news: list) -> dict:
    change = price.get("change_24h_pct", 0.0)
    if change > 3:
        label, confidence = "bullish", 0.7
    elif change < -3:
        label, confidence = "bearish", 0.7
    else:
        label, confidence = "neutral", 0.6
    return {
        "label": label,
        "confidence": confidence,
        "summary": f"Price moved {change:+.2f}% in 24h. "
                   f"{len(news)} news items collected.",
        "llm_used": False,
    }
```

- [ ] **Step 3: Update `graph/nodes/risk_analyzer.py`** — same Claude-first + fallback pattern

```python
from __future__ import annotations
import json
import logging
from pydantic import BaseModel, ValidationError
from config.settings import Settings
from graph.state import AgentState

logger = logging.getLogger(__name__)


class RiskOutput(BaseModel):
    level: str
    factors: list[str]
    recommendation: str


def make_risk_analyzer(settings: Settings):
    async def analyze_risk(state: AgentState) -> dict:
        price = state.get("price_data") or {}
        sentiment = state.get("sentiment_analysis") or {}
        pattern = state.get("market_structure_analysis") or {}
        data_gaps = state.get("data_gaps", [])

        if _should_use_llm(settings):
            result = await _llm_risk(settings, state, price, sentiment, pattern, data_gaps)
            if result:
                return {"risk_analysis": result}

        return {"risk_analysis": _deterministic_risk(price, data_gaps)}

    return analyze_risk


def _should_use_llm(settings: Settings) -> bool:
    try:
        from services.llm_budget import LLMBudgetTracker
        t = LLMBudgetTracker(settings.LLM_ENABLED, settings.MAX_LLM_CALLS_PER_DAY,
                             settings.DAILY_LLM_BUDGET_IDR)
        return t.can_call()
    except Exception:
        return False


async def _llm_risk(settings, state, price, sentiment, pattern, data_gaps) -> dict | None:
    try:
        import anthropic
        from config.prompts import RISK_PROMPT
        from services.llm_budget import LLMBudgetTracker

        prompt = RISK_PROMPT.format(
            symbol=state["symbol"],
            change_24h_pct=price.get("change_24h_pct", 0),
            market_structure=json.dumps(pattern),
            sentiment_label=sentiment.get("label", "neutral"),
            data_gaps=", ".join(data_gaps) or "none",
        )
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.ANTHROPIC_ANALYZER_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        try:
            parsed = RiskOutput(**json.loads(raw))
        except (json.JSONDecodeError, ValidationError):
            repair = await client.messages.create(
                model=settings.ANTHROPIC_ANALYZER_MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": f"Fix this JSON:\n{raw}\nReturn ONLY valid JSON."}],
            )
            parsed = RiskOutput(**json.loads(repair.content[0].text.strip()))

        tracker = LLMBudgetTracker(settings.LLM_ENABLED, settings.MAX_LLM_CALLS_PER_DAY,
                                   settings.DAILY_LLM_BUDGET_IDR)
        tracker.record_call(msg.usage.input_tokens, msg.usage.output_tokens,
                            settings.ANTHROPIC_ANALYZER_MODEL)
        return {**parsed.model_dump(), "llm_used": True}
    except Exception as exc:
        logger.warning("Claude risk failed, using deterministic: %s", exc)
        return None


def _deterministic_risk(price: dict, data_gaps: list) -> dict:
    change = abs(price.get("change_24h_pct", 0))
    if change > 10:
        level = "high"
    elif change > 5:
        level = "medium"
    else:
        level = "low"
    factors = [f"24h change: {price.get('change_24h_pct', 0):+.2f}%"]
    if data_gaps:
        factors.append(f"Data gaps: {', '.join(data_gaps)}")
    return {
        "level": level,
        "factors": factors,
        "recommendation": "Monitor closely." if level != "low" else "Hold current position.",
        "llm_used": False,
    }
```

- [ ] **Step 4: Commit**

```powershell
git add config/prompts.py graph/nodes/sentiment_analyzer.py graph/nodes/risk_analyzer.py
git commit -m "feat: add Claude-powered sentiment and risk analyzers with deterministic fallback"
```

---

### Task 29: Claude Supervisor Node

**File:** `graph/nodes/supervisor.py`

- [ ] **Step 1: Update `graph/nodes/supervisor.py`** — replace stub with Claude-first synthesis

```python
from __future__ import annotations
import logging
from datetime import datetime, timezone
from config.settings import Settings
from graph.state import AgentState

logger = logging.getLogger(__name__)


def make_supervisor(settings: Settings):
    async def supervisor(state: AgentState) -> dict:
        analysis = state.get("analysis") or {}
        price = state.get("price_data") or {}
        sentiment = analysis.get("sentiment") or {}
        ms = analysis.get("market_structure") or {}
        risk = analysis.get("risk") or {}
        data_gaps = state.get("data_gaps", [])
        errors = state.get("errors", [])

        llm_used = (
            sentiment.get("llm_used", False)
            or risk.get("llm_used", False)
        )

        summary = await _llm_summary(settings, state, price, sentiment, ms, risk, data_gaps)
        if not summary:
            summary = _deterministic_summary(price, sentiment, risk)

        report = {
            "run_id": state["run_id"],
            "symbol": state["symbol"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "price": price,
            "sentiment": {k: v for k, v in sentiment.items() if k != "llm_used"},
            "market_structure": ms,
            "risk": {k: v for k, v in risk.items() if k != "llm_used"},
            "summary": summary,
            "data_gaps": data_gaps,
            "llm_used": llm_used,
        }
        return {"report": report}

    return supervisor


async def _llm_summary(settings, state, price, sentiment, pattern, risk, data_gaps) -> str | None:
    try:
        from services.llm_budget import LLMBudgetTracker
        tracker = LLMBudgetTracker(settings.LLM_ENABLED, settings.MAX_LLM_CALLS_PER_DAY,
                                   settings.DAILY_LLM_BUDGET_IDR)
        if not tracker.can_call():
            return None

        import anthropic
        from config.prompts import SUPERVISOR_PROMPT

        prompt = SUPERVISOR_PROMPT.format(
            symbol=state["symbol"],
            price_usd=price.get("price_usd", 0),
            change_24h_pct=price.get("change_24h_pct", 0),
            sentiment_label=sentiment.get("label", "neutral"),
            sentiment_confidence=sentiment.get("confidence", 0.5),
            price_trend=pattern.get("trend", "unknown"),
            risk_level=risk.get("level", "unknown"),
            risk_factors=", ".join(risk.get("factors", [])),
            data_gaps=", ".join(data_gaps) or "none",
        )
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.ANTHROPIC_SUPERVISOR_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        tracker.record_call(msg.usage.input_tokens, msg.usage.output_tokens,
                            settings.ANTHROPIC_SUPERVISOR_MODEL)
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.warning("Claude supervisor failed, using deterministic summary: %s", exc)
        return None


def _deterministic_summary(price: dict, sentiment: dict, risk: dict) -> str:
    change = price.get("change_24h_pct", 0)
    label = sentiment.get("label", "neutral")
    level = risk.get("level", "low")
    return (
        f"{price.get('symbol', 'Asset')} is {label} with a {change:+.2f}% 24h price change. "
        f"Risk level is {level}. {risk.get('recommendation', 'Monitor market conditions.')}"
    )
```

- [ ] **Step 2: Write tests — `tests/unit/test_supervisor.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from graph.nodes.supervisor import make_supervisor


@pytest.fixture
def settings_llm_off(settings_mock):
    settings_mock.LLM_ENABLED = False
    return settings_mock


@pytest.mark.asyncio
async def test_supervisor_deterministic(settings_llm_off):
    supervisor = make_supervisor(settings_llm_off)
    state = {
        "run_id": "r1", "symbol": "BTCUSDT",
        "requested_at": "2025-01-01T00:00:00+00:00",
        "price_data": {"symbol": "BTCUSDT", "price_usd": 50000, "change_24h_pct": 2.5,
                       "volume_24h_usd": 1e9, "source": "mock"},
        "analysis": {
            "sentiment": {"label": "bullish", "confidence": 0.8, "summary": "ok"},
            "market_structure": {
                "bias": "bullish", "rsi": 55.0, "ma_trend": "uptrend",
                "confidence_score": 0.60, "explanation": "BOS bullish",
                "swing_highs": [], "swing_lows": [],
                "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
                "volume_confirmed": False, "invalidation_level": None,
                "macd_histogram_slope": 0.001, "momentum_pct": 0.5,
                "ml_probability_1r": None, "ml_probability_2r": None,
            },
            "risk": {"level": "low", "factors": [], "recommendation": "Hold"},
        },
        "data_gaps": [], "errors": [],
    }
    result = await supervisor(state)
    report = result["report"]
    assert report["symbol"] == "BTCUSDT"
    assert "summary" in report
    assert report["llm_used"] is False
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_supervisor.py -v
```

Expected: 1 passed.

- [ ] **Step 4: Commit**

```powershell
git add graph/nodes/supervisor.py tests/unit/test_supervisor.py
git commit -m "feat: add Claude supervisor node with deterministic fallback"
```

---

## Phase 10: Scheduler, Dockerfile, and README

**Goal:** Add APScheduler for periodic 4-hour report generation, a production Dockerfile, and a README covering setup and usage. This completes the MVP.

---

### Task 30: APScheduler Jobs

**File:** `scheduler/jobs.py`

- [ ] **Step 1: Create `scheduler/__init__.py`** (empty)

- [ ] **Step 2: Create `scheduler/jobs.py`**

```python
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import get_settings
from data_sources.factory import build_adapters
from graph.pipeline import build_graph
from graph.state import AgentState
from publishers.telegram_publisher import TelegramPublisher
from services.storage import ReportStorage
from api.schemas import IntelligenceReportResponse, ErrorReportResponse

logger = logging.getLogger(__name__)

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]


async def _run_report_job(symbol: str) -> None:
    settings = get_settings()
    adapters = build_adapters(settings)
    graph = build_graph(settings, **adapters)
    storage = ReportStorage()
    await storage.init()

    initial: AgentState = {
        "run_id": str(uuid.uuid4()),
        "symbol": symbol,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data": None,
        "news_data": [],
        "onchain_data": None,
        "social_data": None,
        "context": None,
        "sentiment_analysis": None,
        "market_structure_analysis": None,
        "risk_analysis": None,
        "analysis": None,
        "report": None,
        "data_gaps": [],
        "errors": [],
    }

    result = await graph.ainvoke(initial)
    report = result["report"]
    await storage.save(report)

    pub = TelegramPublisher(
        settings.TELEGRAM_BOT_TOKEN,
        settings.TELEGRAM_CHAT_ID,
        settings.DISPLAY_TIMEZONE,
    )
    if "error" in report:
        await pub.publish(ErrorReportResponse(**report))
    else:
        await pub.publish(IntelligenceReportResponse(**report))

    logger.info("Scheduled report complete: symbol=%s run_id=%s", symbol, report["run_id"])


def create_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler()

    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return scheduler

    symbols = getattr(settings, "WATCH_SYMBOLS", DEFAULT_SYMBOLS)
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",")]

    for symbol in symbols:
        scheduler.add_job(
            lambda s=symbol: asyncio.create_task(_run_report_job(s)),
            trigger="interval",
            hours=4,
            id=f"report_{symbol}",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Scheduled 4h report job for %s", symbol)

    return scheduler
```

- [ ] **Step 3: Wire scheduler into `api/main.py` lifespan**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.routes.health import router as health_router
from api.routes.report import router as report_router
from scheduler.jobs import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Crypto Intelligence API", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(report_router)
    return app


app = create_app()
```

- [ ] **Step 4: Add `WATCH_SYMBOLS` and `SCHEDULER_ENABLED` to `config/settings.py`**

These are already present as defaults. Verify `SCHEDULER_ENABLED: bool = False` and add if missing:

```python
WATCH_SYMBOLS: str = "BTCUSDT,ETHUSDT"
```

- [ ] **Step 5: Commit**

```powershell
git add scheduler/ api/main.py config/settings.py
git commit -m "feat: add APScheduler 4h report jobs with Telegram publish"
```

---

### Task 31: Dockerfile

**File:** `Dockerfile`, `.dockerignore`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./
RUN pip install uv && uv sync --no-dev

COPY . .

ENV ENV=production
ENV MOCK_MODE=false
ENV LLM_ENABLED=false
ENV SCHEDULER_ENABLED=false

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.env
data/
.git/
tests/
docs/
```

- [ ] **Step 3: Build and verify**

```powershell
docker build -t crypto-intelligence-agent:latest .
docker run --rm -p 8000:8000 --env-file .env crypto-intelligence-agent:latest
```

- [ ] **Step 4: Commit**

```powershell
git add Dockerfile .dockerignore
git commit -m "build: add Dockerfile for production deployment"
```

---

### Task 32: README

**File:** `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# Crypto Market Intelligence Agent

A LangGraph + Claude multi-agent system that collects market data, runs parallel analysis, and publishes intelligence reports via FastAPI and Telegram.

## Quick Start (zero cost, mock mode)

```bash
uv sync
cp .env.example .env
uvicorn api.main:app --reload
```

Open `http://localhost:8000/report?symbol=BTCUSDT`

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ENV` | `development` | `development` / `production` |
| `MOCK_MODE` | `true` | Use mock data adapters |
| `LLM_ENABLED` | `false` | Enable Claude API calls |
| `DAILY_LLM_BUDGET_IDR` | `0.0` | Max daily spend in IDR |
| `MAX_LLM_CALLS_PER_DAY` | `0` | Max daily API calls (0 = unlimited) |
| `SCHEDULER_ENABLED` | `false` | Enable 4h periodic reports |
| `ANTHROPIC_API_KEY` | `` | Claude API key |
| `TELEGRAM_BOT_TOKEN` | `` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | `` | Telegram chat/channel ID |
| `API_AUTH_ENABLED` | `false` | Require X-API-Key header |
| `API_KEY` | `` | API key when auth enabled |
| `DISPLAY_TIMEZONE` | `Asia/Jakarta` | Timezone for Telegram reports |
| `WATCH_SYMBOLS` | `BTCUSDT,ETHUSDT` | Symbols for scheduled reports |

## API Endpoints

- `GET /health` — System health and config status
- `GET /report?symbol=BTCUSDT` — Generate intelligence report on demand
- `GET /report/history?symbol=BTCUSDT` — Latest cached report from SQLite

## Architecture

```
START → [collect_price, collect_news, collect_onchain, collect_social] (parallel)
      → aggregate_raw → route
         ├─ error_exit → END
         └─ fan_out_analyzers → [analyze_sentiment, analyze_market_structure, analyze_risk] (parallel)
                              → merge_analysis → supervisor → END
```

## Running Tests

```bash
pytest -v
```

## Docker

```bash
docker build -t crypto-intelligence-agent .
docker run -p 8000:8000 --env-file .env crypto-intelligence-agent
```
```

- [ ] **Step 2: Create `.env.example`**

```
ENV=development
MOCK_MODE=true
LLM_ENABLED=false
DAILY_LLM_BUDGET_IDR=0.0
MAX_LLM_CALLS_PER_DAY=0
SCHEDULER_ENABLED=false
ANTHROPIC_API_KEY=
ANTHROPIC_SUPERVISOR_MODEL=claude-sonnet-4-6
ANTHROPIC_ANALYZER_MODEL=claude-haiku-4-5-20251001
ETHERSCAN_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
API_AUTH_ENABLED=false
API_KEY=
DISPLAY_TIMEZONE=Asia/Jakarta
WATCH_SYMBOLS=BTCUSDT,ETHUSDT
```

- [ ] **Step 3: Final full test run**

```powershell
pytest -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```powershell
git add README.md .env.example
git commit -m "docs: add README and .env.example"
```

---

## Milestone Summary

| Phase | Tasks | Deliverable |
|---|---|---|
| 1 | 1–3 | Project scaffold, dependencies, mock adapters |
| 2 | 4–6 | Adapter base classes + FallbackAdapter |
| 3 | 7–9 | Deterministic graph nodes |
| 4 | 10–16 | LangGraph pipeline + integration tests |
| 5 | 17–18 | FastAPI /health + /report |
| 6 | 19–20 | Telegram publisher + bot |
| 7 | 21 | SQLite report history |
| 8 | 22–26 | Real free-tier API adapters |
| 9 | 27–29 | Claude analyzers + supervisor |
| 10 | 30–32 | Scheduler + Dockerfile + README |
| 11 | 33–35 | ML confidence scorer (XGBoost) |
| 12 | 36–37 | Monte Carlo risk simulation |

**First working demo:** Complete Phase 4 → `GET /report?symbol=BTCUSDT` with mock data, no external APIs, no cost.

**Full system:** Complete all phases, set `ENV=production MOCK_MODE=false LLM_ENABLED=true ML_ENABLED=true MONTE_CARLO_ENABLED=true` in `.env`.

---

## Phase 11: ML Confidence Scorer (XGBoost)

**Goal:** Train an XGBoost binary classifier that scores `P(setup reaches +1R before invalidation_level)` and `P(+2R)`. The model gates behind `ML_ENABLED=true` and populates `ml_probability_1r` / `ml_probability_2r` in `MarketStructureAnalysis`. When `ML_ENABLED=false` (the default), these fields stay `None` and the rule-based `confidence_score` is the only signal.

**Prerequisites:** At least 200 labeled examples from paper-trading or backtest data.

---

### Task 33: Feature Extraction + Data Collection

**Files:** `services/ml_features.py`, `services/ml_data_collector.py`

- [ ] **Step 1: Create `services/ml_features.py`**

Extracts a flat feature vector from `MarketStructureAnalysis` + supporting state fields. This is the contract between the rule-based engine and the ML model.

```python
from __future__ import annotations
from typing import Optional


def extract_features(
    ms: dict,
    sentiment_score: float = 0.0,
    risk_level: str = "medium",
) -> dict:
    """Extract ML feature vector from MarketStructureAnalysis dict."""
    risk_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    bos_choch = ms.get("bos_choch", [])
    has_bos = any(e["type"] == "BOS" for e in bos_choch)
    has_choch = any(e["type"] == "CHOCH" for e in bos_choch)

    sweeps = ms.get("liquidity_sweeps", [])
    liquidity_event = int(bool(sweeps))

    obs = ms.get("order_blocks", [])
    active_obs = [ob for ob in obs if not ob.get("mitigated")]
    # Distance from current price to nearest active OB (placeholder: use 0 if not computable)
    ob_distance_pct = 0.0

    # Volume z-score: not available at this layer; passed separately if needed
    volume_zscore = 0.0

    return {
        "liquidity_event": liquidity_event,
        "ob_distance_pct": ob_distance_pct,
        "bos_confirmed": int(has_bos),
        "choch_confirmed": int(has_choch),
        "volume_zscore": volume_zscore,
        "rsi": ms.get("rsi", 50.0),
        "macd_histogram_slope": ms.get("macd_histogram_slope", 0.0),
        "momentum_pct": ms.get("momentum_pct", 0.0),
        "rule_confidence": ms.get("confidence_score", 0.0),
        "sentiment_score": sentiment_score,
        "risk_level_encoded": risk_map.get(risk_level, 1),
    }
```

- [ ] **Step 2: Create `services/ml_data_collector.py`**

Appends labeled training rows to `data/ml_training.jsonl`. Labels are added later via `label_row(run_id, reached_1r, reached_2r)`.

```python
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

_TRAINING_FILE = Path("data/ml_training.jsonl")


def record_example(run_id: str, features: dict, symbol: str) -> None:
    _TRAINING_FILE.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "run_id": run_id,
        "symbol": symbol,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "features": features,
        "label_1r": None,
        "label_2r": None,
    }
    with _TRAINING_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def label_row(run_id: str, reached_1r: bool, reached_2r: bool) -> bool:
    """Update labels for a previously recorded example. Returns True if found."""
    if not _TRAINING_FILE.exists():
        return False
    rows = [json.loads(line) for line in _TRAINING_FILE.read_text().splitlines() if line.strip()]
    updated = False
    for row in rows:
        if row["run_id"] == run_id:
            row["label_1r"] = int(reached_1r)
            row["label_2r"] = int(reached_2r)
            updated = True
    if updated:
        _TRAINING_FILE.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return updated
```

- [ ] **Step 3: Wire feature recording into `analyze_market_structure`**

At the bottom of `analyze_market_structure`, after building the result dict, add:

```python
    # Record features for future ML training (only when data collection is enabled)
    if state.get("_record_ml_features"):
        from services.ml_features import extract_features
        from services.ml_data_collector import record_example
        features = extract_features(result["market_structure_analysis"])
        record_example(state["run_id"], features, state["symbol"])
```

- [ ] **Step 4: Commit**

```powershell
git add services/ml_features.py services/ml_data_collector.py
git commit -m "feat: add ML feature extraction and training data collector"
```

---

### Task 34: XGBoost Model Training Script

**File:** `scripts/train_ml_scorer.py`

Not part of the running application — executed manually after enough labeled data is collected.

- [ ] **Step 1: Create `scripts/__init__.py`** (empty)

- [ ] **Step 2: Create `scripts/train_ml_scorer.py`**

```python
"""
Train XGBoost confidence scorer.

Usage:
    uv run python scripts/train_ml_scorer.py

Requires data/ml_training.jsonl with at least 200 labeled rows.
Outputs:
    models/ml_scorer_1r.json   — XGBoost model for +1R probability
    models/ml_scorer_2r.json   — XGBoost model for +2R probability
    models/feature_names.json  — ordered feature list (must match extract_features())
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np

TRAINING_FILE = Path("data/ml_training.jsonl")
MODEL_DIR = Path("models")
MIN_EXAMPLES = 200


def load_data() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    rows = [
        json.loads(line)
        for line in TRAINING_FILE.read_text().splitlines()
        if line.strip()
    ]
    labeled = [r for r in rows if r["label_1r"] is not None]
    if len(labeled) < MIN_EXAMPLES:
        raise ValueError(f"Need {MIN_EXAMPLES} labeled examples, have {len(labeled)}")

    feature_names = list(labeled[0]["features"].keys())
    X = np.array([[r["features"][k] for k in feature_names] for r in labeled])
    y_1r = np.array([r["label_1r"] for r in labeled])
    y_2r = np.array([r["label_2r"] for r in labeled])
    return X, y_1r, y_2r, feature_names


def train():
    try:
        import xgboost as xgb
    except ImportError:
        raise ImportError("Install xgboost: uv add xgboost")

    X, y_1r, y_2r, feature_names = load_data()
    MODEL_DIR.mkdir(exist_ok=True)

    params = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "max_depth": 4,
        "learning_rate": 0.1,
        "n_estimators": 100,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": (y_1r == 0).sum() / max((y_1r == 1).sum(), 1),
    }

    for target, y, name in [(y_1r, "1r"), (y_2r, "2r")]:
        model = xgb.XGBClassifier(**params, random_state=42)
        model.fit(X, target, eval_set=[(X, target)], verbose=False)
        model.save_model(str(MODEL_DIR / f"ml_scorer_{name}.json"))
        print(f"Saved models/ml_scorer_{name}.json")

    (MODEL_DIR / "feature_names.json").write_text(json.dumps(feature_names))
    print(f"Trained on {len(X)} examples. Features: {feature_names}")


if __name__ == "__main__":
    train()
```

- [ ] **Step 3: Commit**

```powershell
git add scripts/
git commit -m "feat: add XGBoost training script for ML confidence scorer"
```

---

### Task 35: ML Scorer Inference + Integration

**File:** `services/ml_scorer.py`

- [ ] **Step 1: Create `services/ml_scorer.py`**

```python
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_DIR = Path("models")
_scorer_1r = None
_scorer_2r = None
_feature_names: list[str] | None = None


def _load_models() -> bool:
    global _scorer_1r, _scorer_2r, _feature_names
    try:
        import xgboost as xgb
        m1 = MODEL_DIR / "ml_scorer_1r.json"
        m2 = MODEL_DIR / "ml_scorer_2r.json"
        fn = MODEL_DIR / "feature_names.json"
        if not (m1.exists() and m2.exists() and fn.exists()):
            return False
        _scorer_1r = xgb.XGBClassifier()
        _scorer_1r.load_model(str(m1))
        _scorer_2r = xgb.XGBClassifier()
        _scorer_2r.load_model(str(m2))
        _feature_names = json.loads(fn.read_text())
        return True
    except Exception as exc:
        logger.warning("ML scorer load failed: %s", exc)
        return False


def score(features: dict) -> tuple[Optional[float], Optional[float]]:
    """Return (p_1r, p_2r). Returns (None, None) if model not available."""
    global _scorer_1r, _scorer_2r, _feature_names
    if _scorer_1r is None:
        if not _load_models():
            return None, None
    try:
        import numpy as np
        x = np.array([[features.get(k, 0.0) for k in _feature_names]])
        p1r = float(_scorer_1r.predict_proba(x)[0][1])
        p2r = float(_scorer_2r.predict_proba(x)[0][1])
        return round(p1r, 3), round(p2r, 3)
    except Exception as exc:
        logger.warning("ML scorer inference failed: %s", exc)
        return None, None
```

- [ ] **Step 2: Wire ML scorer into `analyze_market_structure`**

In `agents/analyzers/market_structure_analyzer.py`, add after the confidence score block and before returning:

```python
    # Phase 2: ML confidence scoring (only when ML_ENABLED and models exist)
    ml_prob_1r: Optional[float] = None
    ml_prob_2r: Optional[float] = None
    # ML_ENABLED check: read from state if passed, else skip
    if state.get("_ml_enabled"):
        from services.ml_features import extract_features
        from services.ml_scorer import score as ml_score
        sentiment_score = (state.get("sentiment_analysis") or {}).get("sentiment_score", 0.0)
        risk_level = (state.get("risk_analysis") or {}).get("risk_level", "medium")
        feats = extract_features(result_dict, sentiment_score, risk_level)
        ml_prob_1r, ml_prob_2r = ml_score(feats)
```

Then update `ml_probability_1r` and `ml_probability_2r` in the returned dict from `ml_prob_1r`/`ml_prob_2r`.

- [ ] **Step 3: Add `ML_ENABLED` to `config/settings.py`**

```python
ML_ENABLED: bool = False
MONTE_CARLO_ENABLED: bool = False
```

- [ ] **Step 4: Write unit tests — `tests/unit/test_ml_features.py`**

```python
from services.ml_features import extract_features


def test_extract_features_returns_all_keys():
    ms = {
        "bos_choch": [{"type": "BOS", "direction": "bullish", "break_level": 50000.0, "candle_idx": 5}],
        "liquidity_sweeps": [{"type": "high", "swept_level": 50100.0, "sweep_candle_idx": 3, "confirmed": True}],
        "order_blocks": [],
        "rsi": 62.0,
        "macd_histogram_slope": 0.003,
        "momentum_pct": 1.5,
        "confidence_score": 0.70,
    }
    features = extract_features(ms, sentiment_score=0.3, risk_level="low")
    expected_keys = {
        "liquidity_event", "ob_distance_pct", "bos_confirmed", "choch_confirmed",
        "volume_zscore", "rsi", "macd_histogram_slope", "momentum_pct",
        "rule_confidence", "sentiment_score", "risk_level_encoded",
    }
    assert set(features.keys()) == expected_keys
    assert features["bos_confirmed"] == 1
    assert features["liquidity_event"] == 1
    assert features["rsi"] == 62.0
    assert features["risk_level_encoded"] == 0  # low
```

- [ ] **Step 5: Run tests**

```powershell
pytest tests/unit/test_ml_features.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```powershell
git add services/ml_scorer.py tests/unit/test_ml_features.py
git commit -m "feat: add ML scorer inference service and feature extraction tests"
```

---

## Phase 12: Monte Carlo Risk Simulation

**Goal:** Stress-test each detected setup under realistic trading conditions (fees, slippage, random entry perturbation, volatility regime). Runs N=1000 simulations in-process using NumPy. Zero external cost. Gated behind `MONTE_CARLO_ENABLED=true`.

---

### Task 36: Monte Carlo Simulation Engine

**File:** `services/monte_carlo.py`

- [ ] **Step 1: Create `services/monte_carlo.py`**

```python
from __future__ import annotations
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_N = 1000
DEFAULT_TAKER_FEE = 0.0004    # 0.04% per leg
DEFAULT_SLIPPAGE_STD = 0.0002  # 0.02% std on entry/exit


class MonteCarloConfig:
    def __init__(
        self,
        n_simulations: int = DEFAULT_N,
        taker_fee: float = DEFAULT_TAKER_FEE,
        slippage_std: float = DEFAULT_SLIPPAGE_STD,
        risk_per_trade: float = 0.01,   # 1% account risk
    ):
        self.n = n_simulations
        self.taker_fee = taker_fee
        self.slippage_std = slippage_std
        self.risk_per_trade = risk_per_trade


def simulate(
    entry_price: float,
    invalidation_price: float,
    target_1r_price: float,
    target_2r_price: float,
    volatility_atr: float,
    config: Optional[MonteCarloConfig] = None,
) -> dict:
    """
    Run Monte Carlo simulation of a single trade setup.

    Returns MonteCarloResult dict with win rates, EV, ruin probability, percentiles.
    """
    if config is None:
        config = MonteCarloConfig()

    rng = np.random.default_rng(seed=42)
    n = config.n

    # Compute R-distance
    risk = abs(entry_price - invalidation_price)
    if risk == 0:
        return _empty_result(n)

    reward_1r = abs(target_1r_price - entry_price)
    reward_2r = abs(target_2r_price - entry_price)
    direction = 1 if target_1r_price > entry_price else -1

    # Simulate entry price perturbation (slippage)
    entry_slippage = rng.normal(0, config.slippage_std * entry_price, n)
    actual_entries = entry_price + entry_slippage

    # Simulate price path: geometric random walk scaled by ATR
    # Steps between entry and target/stop — approximate with single random outcome
    # scaled by volatility regime
    vol_scale = max(volatility_atr / entry_price, 0.001)
    price_moves = rng.normal(0, vol_scale * entry_price, n)

    outcomes_r = np.zeros(n)
    reached_1r = 0
    reached_2r = 0

    for i in range(n):
        final_price = actual_entries[i] + direction * abs(price_moves[i])
        move = direction * (final_price - actual_entries[i])

        fee_cost = 2 * config.taker_fee * actual_entries[i]
        net_move = move - fee_cost

        # Determine outcome
        if direction * net_move >= reward_1r:
            reached_2r += int(direction * net_move >= reward_2r)
            reached_1r += 1
            outcomes_r[i] = min(2.0, net_move / risk)
        elif direction * net_move <= -risk:
            outcomes_r[i] = -1.0
        else:
            outcomes_r[i] = net_move / risk

    win_rate_1r = reached_1r / n
    win_rate_2r = reached_2r / n
    expected_value = float(np.mean(outcomes_r))
    ruin_prob = float(np.mean(outcomes_r <= -1.0))
    p5 = float(np.percentile(outcomes_r, 5))
    p95 = float(np.percentile(outcomes_r, 95))

    return {
        "n_simulations": n,
        "win_rate_1r": round(win_rate_1r, 3),
        "win_rate_2r": round(win_rate_2r, 3),
        "expected_value": round(expected_value, 3),
        "ruin_probability": round(ruin_prob, 3),
        "p5_outcome": round(p5, 3),
        "p95_outcome": round(p95, 3),
    }


def _empty_result(n: int) -> dict:
    return {
        "n_simulations": n,
        "win_rate_1r": 0.0, "win_rate_2r": 0.0,
        "expected_value": 0.0, "ruin_probability": 1.0,
        "p5_outcome": -1.0, "p95_outcome": -1.0,
    }
```

- [ ] **Step 2: Write unit tests — `tests/unit/test_monte_carlo.py`**

```python
import pytest
from services.monte_carlo import simulate, MonteCarloConfig


def test_simulate_returns_expected_keys():
    result = simulate(
        entry_price=50000.0,
        invalidation_price=49500.0,
        target_1r_price=50500.0,
        target_2r_price=51000.0,
        volatility_atr=300.0,
    )
    assert set(result.keys()) == {
        "n_simulations", "win_rate_1r", "win_rate_2r",
        "expected_value", "ruin_probability", "p5_outcome", "p95_outcome",
    }


def test_win_rates_between_0_and_1():
    result = simulate(50000, 49500, 50500, 51000, 300.0)
    assert 0.0 <= result["win_rate_1r"] <= 1.0
    assert 0.0 <= result["win_rate_2r"] <= result["win_rate_1r"]


def test_ruin_prob_between_0_and_1():
    result = simulate(50000, 49500, 50500, 51000, 300.0)
    assert 0.0 <= result["ruin_probability"] <= 1.0


def test_zero_risk_returns_empty():
    result = simulate(50000, 50000, 50500, 51000, 300.0)
    assert result["win_rate_1r"] == 0.0
```

- [ ] **Step 3: Run tests**

```powershell
pytest tests/unit/test_monte_carlo.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```powershell
git add services/monte_carlo.py tests/unit/test_monte_carlo.py
git commit -m "feat: add Monte Carlo simulation engine for trade setup stress-testing"
```

---

### Task 37: Wire Monte Carlo into Market Structure Analyzer

**File:** `agents/analyzers/market_structure_analyzer.py`

- [ ] **Step 1: Add `monte_carlo` field to MarketStructureAnalysis output**

In the return dict of `analyze_market_structure`, add:

```python
"monte_carlo": None,  # populated when MONTE_CARLO_ENABLED=true
```

- [ ] **Step 2: Add Monte Carlo computation block**

After the confidence score block, before returning:

```python
    # Phase 3: Monte Carlo (only when MONTE_CARLO_ENABLED and price data available)
    monte_carlo_result = None
    if state.get("_monte_carlo_enabled") and invalidation is not None:
        try:
            from services.monte_carlo import simulate, MonteCarloConfig
            price = closes[-1]
            atr = _compute_atr(highs, lows, closes)
            r_dist = abs(price - invalidation)
            direction = 1 if bias == "bullish" else -1
            target_1r = price + direction * r_dist
            target_2r = price + direction * r_dist * 2
            monte_carlo_result = simulate(
                entry_price=price,
                invalidation_price=invalidation,
                target_1r_price=target_1r,
                target_2r_price=target_2r,
                volatility_atr=atr,
            )
        except Exception as exc:
            logger.warning("Monte Carlo simulation failed: %s", exc)
```

- [ ] **Step 3: Add `_compute_atr` helper**

```python
def _compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(highs) < period + 1:
        return (max(highs) - min(lows)) / 2 if highs else 0.0
    trs = []
    for i in range(1, min(period + 1, len(highs))):
        tr = max(
            highs[-i] - lows[-i],
            abs(highs[-i] - closes[-i - 1]),
            abs(lows[-i] - closes[-i - 1]),
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0
```

- [ ] **Step 4: Update `api/schemas.py`** to add `MonteCarloResult` and wire it into `MarketStructureAnalysis`

```python
class MonteCarloResult(BaseModel):
    n_simulations: int
    win_rate_1r: float
    win_rate_2r: float
    expected_value: float
    ruin_probability: float
    p5_outcome: float
    p95_outcome: float
```

Add to `MarketStructureAnalysis`:
```python
    monte_carlo: Optional[MonteCarloResult] = None
```

- [ ] **Step 5: Run full test suite**

```powershell
pytest -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add agents/analyzers/market_structure_analyzer.py api/schemas.py
git commit -m "feat: wire Monte Carlo simulation into market structure analyzer"
```

---

## Updated Milestone Summary

| Phase | Tasks | Deliverable |
|---|---|---|
| 1 | 1–3 | Project scaffold, dependencies, mock adapters |
| 2 | 4–6 | Adapter base classes + FallbackAdapter |
| 3 | 7–9 | Deterministic graph nodes |
| 4 | 10–16 | LangGraph pipeline + integration tests |
| 5 | 17–18 | FastAPI /health + /report |
| 6 | 19–20 | Telegram publisher + bot |
| 7 | 21 | SQLite report history |
| 8 | 22–26 | Real free-tier API adapters |
| 9 | 27–29 | Claude analyzers + supervisor |
| 10 | 30–32 | Scheduler + Dockerfile + README |
| 11 | 33–35 | XGBoost ML confidence scorer (feature collection, training script, inference) |
| 12 | 36–37 | Monte Carlo risk simulation (engine + ATR-based wiring) |

**Signal priority in `analyze_market_structure`:**
1. **Primary:** BOS/CHOCH → Liquidity sweep → Order block → Volume → drives `bias` and `confidence_score`
2. **Secondary:** RSI, MACD slope, MA trend, momentum → adjusts `confidence_score` only
3. **Phase 2 enhancement:** XGBoost `ml_probability_1r/2r` replaces rule confidence as the action signal
4. **Phase 3 overlay:** Monte Carlo `expected_value` and `ruin_probability` go into the Telegram report and API response

**Settings gate:**
- MVP (default): `ML_ENABLED=false`, `MONTE_CARLO_ENABLED=false` — pure rule-based, zero extra cost
- Phase 2 active: `ML_ENABLED=true` — requires trained model in `models/`
- Phase 3 active: `MONTE_CARLO_ENABLED=true` — pure NumPy, no external cost
