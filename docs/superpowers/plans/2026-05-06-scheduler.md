# Phase 7 — APScheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a periodic APScheduler job inside the FastAPI lifespan that runs the full intelligence pipeline for every symbol in `WATCH_SYMBOLS`, saves successful reports to SQLite, and publishes all reports to Telegram.

**Architecture:** `scheduler/job.py` contains the pure async job logic (iterate symbols, run pipeline, save, publish, handle errors). `scheduler/runner.py` is a thin wrapper that creates and configures the `AsyncIOScheduler`. `api/main.py` starts and stops the scheduler inside its existing `lifespan` context manager when `SCHEDULER_ENABLED=true` and Telegram credentials are present.

**Tech Stack:** APScheduler 3.x (`AsyncIOScheduler`, `IntervalTrigger`), python-telegram-bot 20.x (`telegram.Bot`), existing `ReportHistoryRepository`, existing `TelegramPublisher`, `pytest` with `AsyncMock`.

**Spec:** `docs/superpowers/specs/2026-05-06-scheduler-design.md`

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `scheduler/__init__.py` | Empty package marker |
| `scheduler/job.py` | `run_scheduled_reports`, `_run_single`, `_invoke_pipeline`, `_make_error_report` |
| `scheduler/runner.py` | `build_scheduler` — creates and configures `AsyncIOScheduler` |
| `tests/unit/test_scheduler_job.py` | 9 unit tests for all job logic paths |

### Modified files
| File | Change |
|---|---|
| `config/settings.py` | Add `SCHEDULER_INTERVAL_HOURS: int = 4` |
| `tests/unit/test_settings.py` | Add `test_scheduler_interval_hours_default` |
| `api/main.py` | Wire scheduler start/stop into existing `lifespan` |

---

## Task 1: Add `SCHEDULER_INTERVAL_HOURS` to settings

**Files:**
- Modify: `config/settings.py`
- Modify: `tests/unit/test_settings.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_settings.py`:

```python
def test_scheduler_interval_hours_default():
    s = Settings()
    assert s.SCHEDULER_INTERVAL_HOURS == 4
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/unit/test_settings.py::test_scheduler_interval_hours_default -v
```
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'SCHEDULER_INTERVAL_HOURS'`

- [ ] **Step 3: Add field to `config/settings.py`**

Insert after `SCHEDULER_ENABLED: bool = False`:

```python
SCHEDULER_INTERVAL_HOURS: int = 4
```

Full updated block (lines 12–13 area):
```python
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_INTERVAL_HOURS: int = 4
    ML_ENABLED: bool = False
```

- [ ] **Step 4: Run test to confirm it passes**

```
uv run pytest tests/unit/test_settings.py -v
```
Expected: all PASSED (existing 5 + new 1 = 6 total)

- [ ] **Step 5: Commit**

```
git add config/settings.py tests/unit/test_settings.py
git commit -m "feat: add SCHEDULER_INTERVAL_HOURS setting (default 4)"
```

---

## Task 2: Scheduler job module

**Files:**
- Create: `scheduler/__init__.py`
- Create: `scheduler/job.py`
- Create: `tests/unit/test_scheduler_job.py`

- [ ] **Step 1: Create empty package marker**

Create `scheduler/__init__.py` as an empty file.

- [ ] **Step 2: Write all 9 failing tests**

Create `tests/unit/test_scheduler_job.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, call
from config.settings import Settings
from scheduler.job import run_scheduled_reports, _run_single, _make_error_report


def _make_settings(symbols: str = "BTCUSDT,ETHUSDT") -> Settings:
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False, WATCH_SYMBOLS=symbols)


def _make_graph(report: dict | None = None, side_effect=None):
    graph = MagicMock()
    if side_effect is not None:
        graph.ainvoke = AsyncMock(side_effect=side_effect)
    else:
        report = report or {"symbol": "BTCUSDT", "market_bias": "bullish", "error": None}
        graph.ainvoke = AsyncMock(return_value={"report": report})
    return graph


def _make_publisher():
    publisher = MagicMock()
    publisher.publish = AsyncMock()
    return publisher


def _make_repo():
    repo = MagicMock()
    repo.save = AsyncMock()
    return repo


# ---------------------------------------------------------------------------
# run_scheduled_reports
# ---------------------------------------------------------------------------

async def test_run_scheduled_reports_calls_publish_for_each_symbol():
    settings = _make_settings("BTCUSDT,ETHUSDT")
    graph = _make_graph()
    publisher = _make_publisher()
    repo = _make_repo()

    await run_scheduled_reports(settings, graph, publisher, repo)

    assert publisher.publish.call_count == 2
    assert repo.save.call_count == 2


# ---------------------------------------------------------------------------
# _run_single — success path
# ---------------------------------------------------------------------------

async def test_run_single_success_saves_to_repo():
    report = {"symbol": "BTCUSDT", "market_bias": "bullish", "error": None}
    graph = _make_graph(report=report)
    publisher = _make_publisher()
    repo = _make_repo()

    await _run_single("BTCUSDT", graph, publisher, repo)

    repo.save.assert_called_once_with(report)


async def test_run_single_success_publishes():
    report = {"symbol": "BTCUSDT", "market_bias": "bullish", "error": None}
    graph = _make_graph(report=report)
    publisher = _make_publisher()
    repo = _make_repo()

    await _run_single("BTCUSDT", graph, publisher, repo)

    publisher.publish.assert_called_once_with(report)


# ---------------------------------------------------------------------------
# _run_single — retry path
# ---------------------------------------------------------------------------

async def test_run_single_retries_on_first_failure():
    success_report = {"symbol": "BTCUSDT", "market_bias": "neutral", "error": None}
    graph = _make_graph(
        side_effect=[RuntimeError("timeout"), {"report": success_report}]
    )
    publisher = _make_publisher()
    repo = _make_repo()

    await _run_single("BTCUSDT", graph, publisher, repo)

    publisher.publish.assert_called_once()
    call_arg = publisher.publish.call_args[0][0]
    assert call_arg.get("error") is None
    repo.save.assert_called_once()


# ---------------------------------------------------------------------------
# _run_single — double failure path
# ---------------------------------------------------------------------------

async def test_run_single_sends_error_report_after_two_failures():
    graph = _make_graph(side_effect=RuntimeError("network error"))
    publisher = _make_publisher()
    repo = _make_repo()

    await _run_single("BTCUSDT", graph, publisher, repo)

    publisher.publish.assert_called_once()
    call_arg = publisher.publish.call_args[0][0]
    assert call_arg["error"] == "Scheduled report failed after retry"


async def test_run_single_does_not_save_error_report():
    graph = _make_graph(side_effect=RuntimeError("error"))
    publisher = _make_publisher()
    repo = _make_repo()

    await _run_single("BTCUSDT", graph, publisher, repo)

    repo.save.assert_not_called()


# ---------------------------------------------------------------------------
# _run_single — repo failure
# ---------------------------------------------------------------------------

async def test_run_single_repo_failure_still_publishes():
    report = {"symbol": "BTCUSDT", "market_bias": "bullish", "error": None}
    graph = _make_graph(report=report)
    publisher = _make_publisher()
    repo = MagicMock()
    repo.save = AsyncMock(side_effect=Exception("db error"))

    await _run_single("BTCUSDT", graph, publisher, repo)

    publisher.publish.assert_called_once()


# ---------------------------------------------------------------------------
# _run_single — publish failure
# ---------------------------------------------------------------------------

async def test_run_single_logs_when_publish_fails():
    graph = _make_graph()
    publisher = MagicMock()
    publisher.publish = AsyncMock(side_effect=Exception("send failed"))
    repo = _make_repo()

    # Must not raise
    await _run_single("BTCUSDT", graph, publisher, repo)


# ---------------------------------------------------------------------------
# _make_error_report
# ---------------------------------------------------------------------------

def test_make_error_report_shape():
    report = _make_error_report("BTCUSDT")

    assert report["symbol"] == "BTCUSDT"
    assert report["error"] == "Scheduled report failed after retry"
    assert "run_id" in report
    assert "requested_at" in report
    assert "generated_at" in report
    assert report["data_gaps"] == []
```

- [ ] **Step 3: Run to confirm all 9 tests fail**

```
uv run pytest tests/unit/test_scheduler_job.py -v
```
Expected: all 9 FAIL — `ModuleNotFoundError: No module named 'scheduler'`

- [ ] **Step 4: Implement `scheduler/job.py`**

```python
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone

from config.settings import Settings
from publishers.base import ReportPublisher
from storage.report_history import ReportHistoryRepository

logger = logging.getLogger(__name__)


async def run_scheduled_reports(
    settings: Settings,
    graph,
    publisher: ReportPublisher,
    repo: ReportHistoryRepository,
) -> None:
    symbols = [s.strip() for s in settings.WATCH_SYMBOLS.split(",") if s.strip()]
    for symbol in symbols:
        await _run_single(symbol, graph, publisher, repo)


async def _run_single(
    symbol: str,
    graph,
    publisher: ReportPublisher,
    repo: ReportHistoryRepository,
) -> None:
    report = None
    exc_detail = None

    for attempt in (1, 2):
        try:
            report = await _invoke_pipeline(graph, symbol)
            break
        except Exception as exc:
            exc_detail = exc
            logger.warning("Pipeline attempt %d failed for %s: %s", attempt, symbol, exc)
            if attempt == 2:
                report = _make_error_report(symbol)
                logger.error("Pipeline failed after retry for %s: %s", symbol, exc_detail)

    if report is not None and not report.get("error"):
        try:
            await repo.save(report)
        except Exception as exc:
            logger.error("Failed to save report for %s to history: %s", symbol, exc)

    try:
        await publisher.publish(report)
    except Exception:
        logger.error("Telegram send failed for %s", symbol)


async def _invoke_pipeline(graph, symbol: str) -> dict:
    state = {
        "run_id":                    str(uuid.uuid4()),
        "symbol":                    symbol,
        "requested_at":              datetime.now(timezone.utc).isoformat(),
        "price_data":                None,
        "news_data":                 [],
        "onchain_data":              None,
        "social_data":               None,
        "funding_rate_data":         None,
        "context":                   None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":                  None,
        "report":                    None,
        "data_gaps":                 [],
        "errors":                    [],
    }
    result = await graph.ainvoke(state)
    return result["report"]


def _make_error_report(symbol: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_id":       str(uuid.uuid4()),
        "symbol":       symbol,
        "requested_at": now,
        "generated_at": now,
        "error":        "Scheduled report failed after retry",
        "data_gaps":    [],
    }
```

- [ ] **Step 5: Run tests to confirm all 9 pass**

```
uv run pytest tests/unit/test_scheduler_job.py -v
```
Expected: 9 PASSED

- [ ] **Step 6: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```
Expected: all PASSED

- [ ] **Step 7: Commit**

```
git add scheduler/__init__.py scheduler/job.py tests/unit/test_scheduler_job.py
git commit -m "feat: add scheduler job with retry, history persistence, and error handling"
```

---

## Task 3: Scheduler runner

**Files:**
- Create: `scheduler/runner.py`

This module is a thin configuration wrapper — no separate unit tests. Correctness is verified end-to-end in Task 4.

- [ ] **Step 1: Create `scheduler/runner.py`**

```python
from __future__ import annotations
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config.settings import Settings
from publishers.base import ReportPublisher
from storage.report_history import ReportHistoryRepository
from scheduler.job import run_scheduled_reports


def build_scheduler(
    settings: Settings,
    graph,
    publisher: ReportPublisher,
    repo: ReportHistoryRepository,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        func=run_scheduled_reports,
        trigger=IntervalTrigger(hours=settings.SCHEDULER_INTERVAL_HOURS),
        args=[settings, graph, publisher, repo],
        id="crypto_report",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
```

- [ ] **Step 2: Run full unit suite to confirm nothing broken**

```
uv run pytest tests/unit/ -v --tb=short
```
Expected: all PASSED

- [ ] **Step 3: Commit**

```
git add scheduler/runner.py
git commit -m "feat: add build_scheduler with APScheduler interval job"
```

---

## Task 4: Wire scheduler into FastAPI lifespan

**Files:**
- Modify: `api/main.py`

- [ ] **Step 1: Read the current `api/main.py`** before editing to understand exact line structure.

- [ ] **Step 2: Replace `api/main.py` with updated lifespan**

```python
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from config.settings import get_settings
from storage.report_history import ReportHistoryRepository
from api.routes import health, report, history

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    app.state.repo = repo
    logger.info("Report history DB initialized at %s", settings.DB_PATH)

    scheduler = None
    if settings.SCHEDULER_ENABLED:
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            logger.warning(
                "SCHEDULER_ENABLED=true but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing "
                "— scheduler will not start"
            )
        else:
            if settings.SCHEDULER_INTERVAL_HOURS < 1:
                raise ValueError(
                    f"SCHEDULER_INTERVAL_HOURS must be >= 1, "
                    f"got {settings.SCHEDULER_INTERVAL_HOURS}"
                )
            import telegram
            from publishers.telegram_publisher import TelegramPublisher
            from data_sources.factory import build_adapters
            from graph.pipeline import build_graph
            from scheduler.runner import build_scheduler

            bot = telegram.Bot(token=settings.TELEGRAM_BOT_TOKEN)
            publisher = TelegramPublisher(
                bot, settings.TELEGRAM_CHAT_ID, settings.DISPLAY_TIMEZONE
            )
            adapters = build_adapters(settings)
            graph = build_graph(settings, **adapters)
            scheduler = build_scheduler(settings, graph, publisher, repo)
            scheduler.start()
            logger.info(
                "Scheduler started — interval=%dh symbols=%s",
                settings.SCHEDULER_INTERVAL_HOURS,
                settings.WATCH_SYMBOLS,
            )

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


app = FastAPI(
    title="Crypto Intelligence Agent",
    version="0.1.0",
    description="Mock-first LangGraph pipeline for crypto market intelligence.",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(report.router)
app.include_router(history.router)
```

- [ ] **Step 3: Run full test suite — all tests must pass**

```
uv run pytest tests/ -v --tb=short
```
Expected: all 115 tests PASSED (114 existing + 1 new settings test)

The scheduler does not start during tests because test settings have `SCHEDULER_ENABLED=False` (default). No new tests are needed for the lifespan wiring — existing API integration tests cover the non-scheduler boot path.

- [ ] **Step 4: Commit**

```
git add api/main.py
git commit -m "feat: wire APScheduler into FastAPI lifespan with Telegram guard and interval validation"
```

- [ ] **Step 5: Push to GitHub**

```
git push origin main
```

---

## Smoke test (manual, optional)

To verify the scheduler actually fires, temporarily set `SCHEDULER_INTERVAL_HOURS=1` and check logs show `"Scheduler started"` within the first minute after boot. Real Telegram credentials are required — not tested in CI.
