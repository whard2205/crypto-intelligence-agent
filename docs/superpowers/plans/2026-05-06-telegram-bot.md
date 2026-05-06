# Phase 8B — Telegram Bot Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add unit tests for the existing Telegram bot handlers, a `setup_bot_data` helper for FastAPI-integrated lifecycle, and wire the bot into the FastAPI lifespan gated by `TELEGRAM_BOT_ENABLED`.

**Architecture:** A new `TELEGRAM_BOT_ENABLED` setting gates the bot. In FastAPI's `lifespan`, after the scheduler block, the bot starts via PTB v20's async lifecycle (`initialize()` → `setup_bot_data()` → `start()` → `updater.start_polling()`). `setup_bot_data` is an explicit helper in `telegram_bot/main.py` for the integrated path; standalone mode continues to use `_post_init` via `run_polling()`. Handlers are tested by calling them directly with mocked `Update` and `context` — no real PTB Application or network.

**Tech Stack:** python-telegram-bot 20.x (`Application`, `CommandHandler`), pytest with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed), `unittest.mock.AsyncMock`, `unittest.mock.patch`. Run all tests with `uv run pytest`.

**Spec:** `docs/superpowers/specs/2026-05-06-telegram-bot-design.md`

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `tests/unit/test_telegram_bot.py` | 11 unit tests for handlers, `build_bot`, `setup_bot_data` |

### Modified files
| File | Change |
|---|---|
| `config/settings.py` | Add `TELEGRAM_BOT_ENABLED: bool = False` after `SCHEDULER_ENABLED` |
| `tests/unit/test_settings.py` | Add `assert s.TELEGRAM_BOT_ENABLED is False` to `test_defaults_are_cost_safe` |
| `telegram_bot/main.py` | Add `setup_bot_data(application, settings)` async helper |
| `api/main.py` | Add bot lifecycle block to lifespan (after scheduler block, before `yield`) |

---

## Task 1: `TELEGRAM_BOT_ENABLED` setting

**Files:**
- Modify: `config/settings.py`
- Modify: `tests/unit/test_settings.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_settings.py`, add `assert s.TELEGRAM_BOT_ENABLED is False` to the existing `test_defaults_are_cost_safe`. The full updated function:

```python
def test_defaults_are_cost_safe():
    s = Settings()
    assert s.ENV == "development"
    assert s.MOCK_MODE is True
    assert s.LLM_ENABLED is False
    assert s.DAILY_LLM_BUDGET_IDR == 0.0
    assert s.MAX_LLM_CALLS_PER_DAY == 0
    assert s.SCHEDULER_ENABLED is False
    assert s.SCHEDULER_INTERVAL_HOURS == 4
    assert s.TELEGRAM_BOT_ENABLED is False
    assert s.ML_ENABLED is False
    assert s.MONTE_CARLO_ENABLED is False
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/unit/test_settings.py::test_defaults_are_cost_safe -v
```

Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'TELEGRAM_BOT_ENABLED'`

- [ ] **Step 3: Add field to `config/settings.py`**

Insert `TELEGRAM_BOT_ENABLED: bool = False` after `SCHEDULER_ENABLED`. The updated block:

```python
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_INTERVAL_HOURS: int = 4
    TELEGRAM_BOT_ENABLED: bool = False
    ML_ENABLED: bool = False
```

- [ ] **Step 4: Run all settings tests to confirm pass**

```
uv run pytest tests/unit/test_settings.py -v
```

Expected: all PASSED (6 tests)

- [ ] **Step 5: Commit**

```
git add config/settings.py tests/unit/test_settings.py
git commit -m "feat: add TELEGRAM_BOT_ENABLED setting (default false)"
```

---

## Task 2: `setup_bot_data` helper + 11 unit tests

**Files:**
- Create: `tests/unit/test_telegram_bot.py`
- Modify: `telegram_bot/main.py`

The test file imports `setup_bot_data` which does not exist yet — all 11 tests will fail with `ImportError` until Step 3.

- [ ] **Step 1: Create `tests/unit/test_telegram_bot.py` with all 11 tests**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import Settings
from telegram_bot.main import (
    HELP_TEXT,
    build_bot,
    help_command,
    report_command,
    setup_bot_data,
    start_command,
)


def _make_settings(symbols: str = "BTCUSDT,ETHUSDT") -> Settings:
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False, WATCH_SYMBOLS=symbols)


def _make_report(symbol: str = "BTCUSDT") -> dict:
    return {
        "run_id": "test-run-id",
        "symbol": symbol,
        "requested_at": "2026-05-06T00:00:00+00:00",
        "generated_at": "2026-05-06T00:00:00+00:00",
        "market_bias": "bullish",
        "confidence_score": 0.75,
        "key_signals": ["RSI oversold"],
        "risk_warnings": [],
        "narrative": "Test narrative.",
        "data_gaps": [],
        "error": None,
        "llm_used": False,
        "price_source": "mock",
        "news_source": "mock",
        "analysis_engine": "rule-based",
        "funding_source": "unavailable",
    }


def _make_graph(report: dict | None = None, side_effect=None):
    graph = MagicMock()
    if side_effect is not None:
        graph.ainvoke = AsyncMock(side_effect=side_effect)
    else:
        graph.ainvoke = AsyncMock(return_value={"report": report or _make_report()})
    return graph


def _make_repo():
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.get_latest = AsyncMock(return_value=[])
    return repo


def _make_update():
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _make_context(settings: Settings, graph, repo=None, args=None):
    context = MagicMock()
    context.bot_data = {"settings": settings, "graph": graph, "repo": repo}
    context.args = args or []
    return context


# ---------------------------------------------------------------------------
# help / start
# ---------------------------------------------------------------------------

async def test_help_command_sends_help_text():
    update = _make_update()
    context = MagicMock()

    await help_command(update, context)

    update.message.reply_text.assert_called_once_with(HELP_TEXT, parse_mode="HTML")


async def test_start_command_sends_help_text():
    update = _make_update()
    context = MagicMock()

    await start_command(update, context)

    update.message.reply_text.assert_called_once_with(HELP_TEXT, parse_mode="HTML")


# ---------------------------------------------------------------------------
# report_command — validation
# ---------------------------------------------------------------------------

async def test_report_command_invalid_symbol_sends_error():
    settings = _make_settings()
    graph = _make_graph()
    update = _make_update()
    context = _make_context(settings, graph, args=["bad!"])

    await report_command(update, context)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "Invalid symbol" in reply_text
    graph.ainvoke.assert_not_called()


# ---------------------------------------------------------------------------
# report_command — no-args (all symbols)
# ---------------------------------------------------------------------------

async def test_report_command_no_args_sends_generating_message():
    settings = _make_settings("BTCUSDT,ETHUSDT")
    graph = _make_graph()
    repo = _make_repo()
    update = _make_update()
    context = _make_context(settings, graph, repo=repo, args=[])

    await report_command(update, context)

    first_call_arg = update.message.reply_text.call_args_list[0][0][0]
    assert "⏳" in first_call_arg


async def test_report_command_no_args_calls_pipeline_for_all_symbols():
    settings = _make_settings("BTCUSDT,ETHUSDT")
    graph = _make_graph()
    repo = _make_repo()
    update = _make_update()
    context = _make_context(settings, graph, repo=repo, args=[])

    await report_command(update, context)

    assert graph.ainvoke.call_count == 2


# ---------------------------------------------------------------------------
# report_command — success path
# ---------------------------------------------------------------------------

async def test_report_command_valid_symbol_invokes_pipeline():
    settings = _make_settings()
    graph = _make_graph()
    repo = _make_repo()
    update = _make_update()
    context = _make_context(settings, graph, repo=repo, args=["BTCUSDT"])

    await report_command(update, context)

    graph.ainvoke.assert_called_once()


async def test_report_command_pipeline_success_saves_to_repo():
    settings = _make_settings()
    graph = _make_graph()
    repo = _make_repo()
    update = _make_update()
    context = _make_context(settings, graph, repo=repo, args=["BTCUSDT"])

    await report_command(update, context)

    repo.save.assert_called_once()


# ---------------------------------------------------------------------------
# report_command — failure path
# ---------------------------------------------------------------------------

async def test_report_command_pipeline_failure_sends_error():
    settings = _make_settings()
    graph = _make_graph(side_effect=RuntimeError("network error"))
    repo = _make_repo()
    update = _make_update()
    context = _make_context(settings, graph, repo=repo, args=["BTCUSDT"])

    await report_command(update, context)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "❌" in reply_text


# ---------------------------------------------------------------------------
# report_command — no repo
# ---------------------------------------------------------------------------

async def test_report_command_no_repo_skips_save():
    settings = _make_settings()
    graph = _make_graph()
    update = _make_update()
    context = _make_context(settings, graph, repo=None, args=["BTCUSDT"])

    await report_command(update, context)

    update.message.reply_text.assert_called()


# ---------------------------------------------------------------------------
# build_bot
# ---------------------------------------------------------------------------

def test_build_bot_raises_without_token():
    settings = Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False, TELEGRAM_BOT_TOKEN="")

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        build_bot(settings)


# ---------------------------------------------------------------------------
# setup_bot_data
# ---------------------------------------------------------------------------

async def test_setup_bot_data_sets_repo_in_bot_data():
    settings = _make_settings()
    application = MagicMock()
    application.bot_data = {}

    with patch("telegram_bot.main.ReportHistoryRepository") as MockRepo:
        mock_repo_instance = MagicMock()
        mock_repo_instance.init_db = AsyncMock()
        MockRepo.return_value = mock_repo_instance

        await setup_bot_data(application, settings)

    assert application.bot_data["repo"] is mock_repo_instance
    MockRepo.assert_called_once_with(settings.DB_PATH)
```

- [ ] **Step 2: Run to confirm all 11 tests fail**

```
uv run pytest tests/unit/test_telegram_bot.py -v
```

Expected: all 11 FAIL — `ImportError: cannot import name 'setup_bot_data' from 'telegram_bot.main'`

- [ ] **Step 3: Add `setup_bot_data` to `telegram_bot/main.py`**

Add the import for `Settings` is already present. Insert the new async function after `_post_init` and before `build_bot`. The full new function:

```python
async def setup_bot_data(application: Application, settings: Settings) -> None:
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    application.bot_data["repo"] = repo
    logger.info("Report history DB ready at %s", settings.DB_PATH)
```

The exact insertion point in `telegram_bot/main.py` — after the closing of `_post_init` (line ~103) and before `def build_bot`:

```python
# ---------------------------------------------------------------------------
# Async post-init hook: runs in the bot's event loop before polling starts
# ---------------------------------------------------------------------------

async def _post_init(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    application.bot_data["repo"] = repo
    logger.info("Report history DB ready at %s", settings.DB_PATH)


# ---------------------------------------------------------------------------
# Bot data initializer for FastAPI-integrated lifecycle
# ---------------------------------------------------------------------------

async def setup_bot_data(application: Application, settings: Settings) -> None:
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    application.bot_data["repo"] = repo
    logger.info("Report history DB ready at %s", settings.DB_PATH)


# ---------------------------------------------------------------------------
# Bot builder
# ---------------------------------------------------------------------------
```

- [ ] **Step 4: Run tests to confirm all 11 pass**

```
uv run pytest tests/unit/test_telegram_bot.py -v
```

Expected: 11 PASSED

- [ ] **Step 5: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```
git add telegram_bot/main.py tests/unit/test_telegram_bot.py
git commit -m "feat: add setup_bot_data helper and telegram bot unit tests"
```

---

## Task 3: Wire bot into FastAPI lifespan

**Files:**
- Modify: `api/main.py`

The bot does not start during tests because `TELEGRAM_BOT_ENABLED=False` is the default. No new tests are needed for the lifespan wiring — existing API integration tests cover the non-bot boot path.

- [ ] **Step 1: Update `api/main.py` lifespan**

The full updated `api/main.py`:

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

    bot_application = None
    if settings.TELEGRAM_BOT_ENABLED:
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning(
                "TELEGRAM_BOT_ENABLED=true but TELEGRAM_BOT_TOKEN is missing "
                "— bot will not start"
            )
        else:
            from telegram_bot.main import build_bot, setup_bot_data
            bot_application = build_bot(settings)
            await bot_application.initialize()
            await setup_bot_data(bot_application, settings)
            await bot_application.start()
            await bot_application.updater.start_polling()
            logger.info("Telegram bot started — polling for commands")

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    if bot_application is not None:
        if bot_application.updater:
            await bot_application.updater.stop()
        await bot_application.stop()
        await bot_application.shutdown()
        logger.info("Telegram bot stopped")


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

- [ ] **Step 2: Run full test suite**

```
uv run pytest tests/ -v --tb=short
```

Expected: all PASSED (`TELEGRAM_BOT_ENABLED=False` by default → bot block never entered in tests)

- [ ] **Step 3: Commit**

```
git add api/main.py
git commit -m "feat: wire Telegram bot into FastAPI lifespan with TELEGRAM_BOT_ENABLED gate"
```

- [ ] **Step 4: Push to GitHub**

```
git push origin main
```
