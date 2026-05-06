# Phase 7 — APScheduler: Periodic Telegram Reports

**Date:** 2026-05-06
**Status:** Approved, pending implementation

---

## Overview

Add a periodic scheduler that runs the full intelligence pipeline for every symbol in `WATCH_SYMBOLS` and publishes results to Telegram. The scheduler runs inside the FastAPI process, started and stopped via the existing `lifespan` context manager. It is gated behind `SCHEDULER_ENABLED=true` and requires both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to be set.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Scheduler placement | Embedded in FastAPI lifespan | Single process, no orchestration overhead; infrastructure already in place |
| Interval configuration | `SCHEDULER_INTERVAL_HOURS: int = 4` env var | Configurable without redeploy; default 4 hours balances frequency vs. noise |
| Symbols | All `WATCH_SYMBOLS` per run | One message per symbol per tick; `WATCH_SYMBOLS` already supports CSV list |
| Error handling | Retry once → error report → log | Retry handles transient failures; error report to Telegram makes failures visible |
| Graph lifetime | Built once at scheduler start, reused each tick | Avoids re-importing adapters on every run; consistent with how the API works |
| Telegram guard | `SCHEDULER_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID` | Both are required; server must not crash if either is missing |

---

## Files

### New files

| File | Purpose |
|---|---|
| `scheduler/__init__.py` | Empty — makes `scheduler` a package |
| `scheduler/job.py` | Core job: iterate symbols, invoke pipeline, publish, handle errors |
| `scheduler/runner.py` | APScheduler setup and lifecycle management |
| `tests/unit/test_scheduler_job.py` | Unit tests for job logic |

### Modified files

| File | Change |
|---|---|
| `config/settings.py` | Add `SCHEDULER_INTERVAL_HOURS: int = 4` |
| `api/main.py` | Wire scheduler start/stop into existing lifespan |

---

## Settings Addition

```python
SCHEDULER_INTERVAL_HOURS: int = 4
```

`SCHEDULER_ENABLED` already exists. `WATCH_SYMBOLS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `DISPLAY_TIMEZONE` are already present and consumed as-is.

---

## Job Logic

### `scheduler/job.py`

```python
async def run_scheduled_reports(settings: Settings, graph, publisher: ReportPublisher) -> None:
    symbols = [s.strip() for s in settings.WATCH_SYMBOLS.split(",") if s.strip()]
    for symbol in symbols:
        await _run_single(symbol, graph, publisher)


async def _run_single(symbol: str, graph, publisher: ReportPublisher) -> None:
    report = None
    for attempt in (1, 2):
        try:
            report = await _invoke_pipeline(graph, symbol)
            break
        except Exception as exc:
            logger.warning("Pipeline attempt %d failed for %s: %s", attempt, symbol, exc)
            if attempt == 2:
                report = _make_error_report(symbol, exc)

    try:
        await publisher.publish(report)
    except Exception:
        logger.error("Telegram send failed for %s", symbol)


async def _invoke_pipeline(graph, symbol: str) -> dict:
    import uuid
    from datetime import datetime, timezone
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


def _make_error_report(symbol: str, exc: Exception) -> dict:
    from datetime import datetime, timezone
    return {
        "symbol":       symbol,
        "error":        str(exc),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_gaps":    [],
    }
```

---

## Scheduler Runner

### `scheduler/runner.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config.settings import Settings
from publishers.base import ReportPublisher
from scheduler.job import run_scheduled_reports


def build_scheduler(settings: Settings, graph, publisher: ReportPublisher) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        func=run_scheduled_reports,
        trigger=IntervalTrigger(hours=settings.SCHEDULER_INTERVAL_HOURS),
        args=[settings, graph, publisher],
        id="crypto_report",
        replace_existing=True,
    )
    return scheduler
```

---

## Lifespan Wiring

### `api/main.py` — updated lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    app.state.repo = repo
    logger.info("Report history DB initialized at %s", settings.DB_PATH)

    scheduler = None
    if settings.SCHEDULER_ENABLED and settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        import telegram
        from publishers.telegram_publisher import TelegramPublisher
        from data_sources.factory import build_adapters
        from graph.pipeline import build_graph
        from scheduler.runner import build_scheduler

        bot = telegram.Bot(token=settings.TELEGRAM_BOT_TOKEN)
        publisher = TelegramPublisher(bot, settings.TELEGRAM_CHAT_ID, settings.DISPLAY_TIMEZONE)
        adapters = build_adapters(settings)
        graph = build_graph(settings, **adapters)
        scheduler = build_scheduler(settings, graph, publisher)
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
```

Imports are inside the `if` block to avoid loading Telegram/pipeline dependencies when the scheduler is disabled.

---

## Error Handling Details

| Scenario | Behavior |
|---|---|
| Pipeline raises on attempt 1 | Log WARNING, retry |
| Pipeline raises on attempt 2 | Build error report dict, proceed to publish |
| `publisher.publish` raises | Log ERROR, continue to next symbol |
| `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` missing | Scheduler not started; server boots normally |
| `SCHEDULER_ENABLED=false` | Scheduler not started; no Telegram bot instantiated |

---

## Test Plan

### `tests/unit/test_scheduler_job.py`

| Test | Scenario | Assertion |
|---|---|---|
| `test_run_scheduled_reports_calls_publish_for_each_symbol` | `WATCH_SYMBOLS=BTCUSDT,ETHUSDT`, pipeline succeeds | `publisher.publish` called twice |
| `test_run_single_success` | pipeline returns report | `publisher.publish` called with that report |
| `test_run_single_retries_on_first_failure` | pipeline raises once then succeeds | `publish` called with success report |
| `test_run_single_sends_error_report_after_two_failures` | pipeline raises twice | `publish` called with dict containing `"error"` key |
| `test_run_single_logs_when_publish_fails` | publisher raises | no exception raised; error logged |
| `test_make_error_report_shape` | any exception | returns dict with `symbol`, `error`, `generated_at`, `data_gaps` |

All tests use `AsyncMock` for graph (`graph.ainvoke`) and publisher (`publisher.publish`). No real pipeline, no real Telegram.

---

## Out of Scope

- Persistent job store (Redis/SQLite APScheduler store)
- Cron-style schedule (specific times of day)
- Per-symbol interval configuration
- Telegram bot command handling (e.g. `/report` command)
- Report deduplication (detecting if bias changed since last run)
- LLM integration
