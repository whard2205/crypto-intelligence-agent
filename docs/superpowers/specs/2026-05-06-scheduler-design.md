# Phase 7 — APScheduler: Periodic Telegram Reports

**Date:** 2026-05-06
**Status:** Approved, pending implementation

---

## Overview

Add a periodic scheduler that runs the full intelligence pipeline for every symbol in `WATCH_SYMBOLS`, saves successful reports to SQLite history, and publishes results to Telegram. The scheduler runs inside the FastAPI process, started and stopped via the existing `lifespan` context manager. It is gated behind `SCHEDULER_ENABLED=true` and requires both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to be set.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Scheduler placement | Embedded in FastAPI lifespan | Single process, no orchestration overhead; infrastructure already in place |
| Interval configuration | `SCHEDULER_INTERVAL_HOURS: int = 4` env var | Configurable without redeploy; default 4 hours balances frequency vs. noise |
| Interval validation | `>= 1` at startup | Prevents misconfiguration (0 or negative would spin the scheduler) |
| Symbols | All `WATCH_SYMBOLS` per run | One message per symbol per tick; `WATCH_SYMBOLS` already supports CSV list |
| Error handling | Retry once → error report → log | Retry handles transient failures; error report to Telegram makes failures visible |
| History persistence | Successful reports saved to `ReportHistoryRepository` | Scheduled reports must appear in `/history`; error reports are not saved |
| Graph + repo lifetime | Built once at scheduler start, reused each tick | Avoids re-importing adapters on every run; consistent with how the API works |
| Telegram guard | `SCHEDULER_ENABLED and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID` | Both are required; missing either logs a warning and skips scheduler start without crashing |
| Job overlap protection | `max_instances=1`, `coalesce=True` | If a run is still in progress when the next interval fires, skip rather than overlap |
| Error message in Telegram | Short user-facing string, not full traceback | Full tracebacks are noisy in chat; real details go to server logs |

---

## Files

### New files

| File | Purpose |
|---|---|
| `scheduler/__init__.py` | Empty — makes `scheduler` a package |
| `scheduler/job.py` | Core job: iterate symbols, invoke pipeline, save, publish, handle errors |
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

Interval validation happens at scheduler start (in lifespan), not in the `Settings` class:

```python
if settings.SCHEDULER_INTERVAL_HOURS < 1:
    raise ValueError(f"SCHEDULER_INTERVAL_HOURS must be >= 1, got {settings.SCHEDULER_INTERVAL_HOURS}")
```

---

## Job Logic

### `scheduler/job.py`

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

    # Save successful report to history (not error reports)
    if report is not None and not report.get("error"):
        try:
            await repo.save(report)
        except Exception as exc:
            logger.error("Failed to save report for %s to history: %s", symbol, exc)

    # Publish to Telegram regardless (success or error report)
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

**Key behaviors:**
- `_make_error_report` uses the short user-facing string `"Scheduled report failed after retry"` — real exception details are logged at ERROR level, not sent to Telegram.
- `repo.save` is only called when `report.get("error")` is falsy — error reports are published but not stored.
- If `repo.save` raises, the error is logged and publish still proceeds.

---

## Scheduler Runner

### `scheduler/runner.py`

```python
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

`max_instances=1` — at most one run active at a time. `coalesce=True` — if a tick was missed while a run was in progress, execute once on recovery rather than catching up on every missed tick.

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
    if settings.SCHEDULER_ENABLED:
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            logger.warning(
                "SCHEDULER_ENABLED=true but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing "
                "— scheduler will not start"
            )
        else:
            if settings.SCHEDULER_INTERVAL_HOURS < 1:
                raise ValueError(
                    f"SCHEDULER_INTERVAL_HOURS must be >= 1, got {settings.SCHEDULER_INTERVAL_HOURS}"
                )
            import telegram
            from publishers.telegram_publisher import TelegramPublisher
            from data_sources.factory import build_adapters
            from graph.pipeline import build_graph
            from scheduler.runner import build_scheduler

            bot = telegram.Bot(token=settings.TELEGRAM_BOT_TOKEN)
            publisher = TelegramPublisher(bot, settings.TELEGRAM_CHAT_ID, settings.DISPLAY_TIMEZONE)
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
```

Imports are inside the `if` block to avoid loading Telegram/pipeline dependencies when the scheduler is disabled.

---

## Error Handling Details

| Scenario | Behavior |
|---|---|
| Pipeline raises on attempt 1 | Log WARNING, retry |
| Pipeline raises on attempt 2 | Log ERROR with real exception; build error report with short user-facing message |
| `repo.save` raises | Log ERROR, continue to publish |
| `publisher.publish` raises | Log ERROR, continue to next symbol |
| `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` missing | Log WARNING; scheduler not started; server boots normally |
| `SCHEDULER_ENABLED=false` | Scheduler not started; no Telegram bot instantiated |
| `SCHEDULER_INTERVAL_HOURS < 1` | `ValueError` raised at startup — misconfiguration must be fixed before server can run |
| Run still in progress when next tick fires | APScheduler skips tick (`max_instances=1`, `coalesce=True`) |

---

## Test Plan

### `tests/unit/test_scheduler_job.py`

All tests use `AsyncMock` for `graph.ainvoke` and `publisher.publish`, and `AsyncMock` for `repo.save`. No real pipeline, no real Telegram, no real database.

| Test | Scenario | Assertion |
|---|---|---|
| `test_run_scheduled_reports_calls_publish_for_each_symbol` | `WATCH_SYMBOLS=BTCUSDT,ETHUSDT`, pipeline succeeds | `publisher.publish` called twice |
| `test_run_single_success_saves_to_repo` | pipeline returns successful report | `repo.save` called with that report |
| `test_run_single_success_publishes` | pipeline returns successful report | `publisher.publish` called with that report |
| `test_run_single_retries_on_first_failure` | pipeline raises once then succeeds | `publish` called with success report; `repo.save` called |
| `test_run_single_sends_error_report_after_two_failures` | pipeline raises twice | `publish` called with dict containing `"error"` key |
| `test_run_single_does_not_save_error_report` | pipeline raises twice | `repo.save` NOT called |
| `test_run_single_repo_failure_still_publishes` | pipeline succeeds, `repo.save` raises | `publisher.publish` still called |
| `test_run_single_logs_when_publish_fails` | publisher raises | no exception propagated; error logged |
| `test_make_error_report_shape` | call `_make_error_report("BTCUSDT")` | returns dict with `run_id`, `symbol`, `requested_at`, `generated_at`, `error`, `data_gaps` keys |

---

## Out of Scope

- Persistent job store (Redis/SQLite APScheduler store)
- Cron-style schedule (specific times of day)
- Per-symbol interval configuration
- Telegram bot command handling (e.g. `/report` command)
- Report deduplication (detecting if bias changed since last run)
- LLM integration
- HMM regime detection
- XGBoost / Monte Carlo
