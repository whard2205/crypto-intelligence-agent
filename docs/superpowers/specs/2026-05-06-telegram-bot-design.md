# Phase 8B — Telegram Bot Commands

**Date:** 2026-05-06
**Status:** Approved, pending implementation

---

## Overview

Add unit tests for the existing Telegram bot command handlers and integrate the bot into the FastAPI lifespan so it starts and stops automatically alongside the API server. The bot is gated by a new `TELEGRAM_BOT_ENABLED` setting. The standalone entry point (`python -m telegram_bot.main`) continues to work independently.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Integration gate | `TELEGRAM_BOT_ENABLED` (new) + `TELEGRAM_BOT_TOKEN` | Token alone is insufficient — the scheduler also uses the token for sending; polling should only start when explicitly enabled |
| PTB v20 lifecycle | `initialize()` → `setup_bot_data()` → `start()` → `updater.start_polling()` | `run_polling()` calls `asyncio.run()` internally and cannot be used inside an existing event loop |
| `post_init` vs `setup_bot_data` | `post_init` stays for standalone; `setup_bot_data` used for integrated | PTB's `initialize()` does not call `post_init`; integrated lifecycle must initialize bot_data explicitly |
| Repo sharing | Bot creates its own `ReportHistoryRepository` instance | Both instances point to the same SQLite file; no coupling needed |
| Token-missing behavior | Log WARNING; lifespan continues | Bot is optional; server must not crash due to missing bot credentials |
| Test approach | Call handlers directly with mocked `Update` and `context` | No real PTB Application or network needed; fast and isolated |

---

## Files

### New files

| File | Purpose |
|---|---|
| `tests/unit/test_telegram_bot.py` | 11 unit tests for handlers, `build_bot`, `setup_bot_data` |

### Modified files

| File | Change |
|---|---|
| `config/settings.py` | Add `TELEGRAM_BOT_ENABLED: bool = False` |
| `tests/unit/test_settings.py` | Add `assert s.TELEGRAM_BOT_ENABLED is False` to `test_defaults_are_cost_safe` |
| `telegram_bot/main.py` | Add `setup_bot_data(application, settings)` helper |
| `api/main.py` | Add bot lifecycle block to lifespan |

---

## Settings Addition

```python
TELEGRAM_BOT_ENABLED: bool = False
```

Added after `SCHEDULER_ENABLED` in `config/settings.py`. `TELEGRAM_BOT_TOKEN` already exists and is consumed as-is.

---

## `setup_bot_data` Helper

```python
# telegram_bot/main.py
async def setup_bot_data(application: Application, settings: Settings) -> None:
    repo = ReportHistoryRepository(settings.DB_PATH)
    await repo.init_db()
    application.bot_data["repo"] = repo
    logger.info("Report history DB ready at %s", settings.DB_PATH)
```

**Key behaviors:**
- Creates a fresh `ReportHistoryRepository` (independent from the API's own instance)
- Sets `application.bot_data["repo"]` so `report_command` can access it
- Used by the integrated FastAPI lifecycle; standalone mode continues to use `_post_init` via `run_polling()`

`_post_init` is unchanged and stays registered in `build_bot()`.

---

## Lifespan Wiring

### `api/main.py` — updated lifespan

```python
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

if bot_application is not None:
    if bot_application.updater:
        await bot_application.updater.stop()
    await bot_application.stop()
    await bot_application.shutdown()
    logger.info("Telegram bot stopped")
```

Imports are inside the `if` block to avoid loading PTB dependencies when the bot is disabled.

The bot lifecycle block is added after the scheduler block and before `yield`.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `TELEGRAM_BOT_ENABLED=false` | Bot not started; no log message |
| `TELEGRAM_BOT_ENABLED=true`, token missing | Log WARNING; lifespan continues normally |
| `TELEGRAM_BOT_ENABLED=true`, token present | Bot starts; polls for commands |
| Bot startup raises | Exception propagates — misconfiguration must be fixed before server boots |
| Handler pipeline failure | Caught per-symbol; `❌` error reply sent; other symbols unaffected |
| `repo.save` failure in handler | Logged; Telegram reply still sent |
| `inject_trend_signal` failure | Handled inside helper (logs warning, returns report unchanged) |

---

## Operational Constraints

- **Do not run the FastAPI-integrated bot and `python -m telegram_bot.main` simultaneously with the same token.** Both processes would poll the same Telegram update queue; each would receive only a random subset of commands.
- **Avoid `uvicorn --reload` when `TELEGRAM_BOT_ENABLED=true`.** Each reload spawns a new polling connection before the old one tears down, causing duplicate command handlers and unpredictable behavior.

---

## Test Plan

### `tests/unit/test_settings.py`

Add to `test_defaults_are_cost_safe`:
```python
assert s.TELEGRAM_BOT_ENABLED is False
```

### `tests/unit/test_telegram_bot.py`

All tests use `AsyncMock` for `update.message.reply_text`, `graph.ainvoke`, `repo.save`, and `repo.get_latest`. No real PTB Application, no real Telegram network.

| Test | Scenario | Assertion |
|---|---|---|
| `test_help_command_sends_help_text` | call `help_command` | `reply_text` called with `HELP_TEXT` |
| `test_start_command_sends_help_text` | call `start_command` | same output as help |
| `test_report_command_invalid_symbol_sends_error` | args=`["bad!"]` | error message containing "Invalid symbol" sent |
| `test_report_command_no_args_sends_generating_message` | no args, `WATCH_SYMBOLS="BTCUSDT,ETHUSDT"` | "⏳ Generating" reply sent |
| `test_report_command_no_args_calls_pipeline_for_all_symbols` | no args, `WATCH_SYMBOLS="BTCUSDT,ETHUSDT"` | `graph.ainvoke` called twice (once per symbol) |
| `test_report_command_valid_symbol_invokes_pipeline` | args=`["BTCUSDT"]`, pipeline success | `graph.ainvoke` called once |
| `test_report_command_pipeline_success_saves_to_repo` | args=`["BTCUSDT"]`, pipeline success | `repo.save` called with report |
| `test_report_command_pipeline_failure_sends_error` | `graph.ainvoke` raises | `❌` error reply sent; no exception propagated |
| `test_report_command_no_repo_skips_save` | `repo=None`, pipeline success | reply sent; `repo.save` never called |
| `test_build_bot_raises_without_token` | `TELEGRAM_BOT_TOKEN=""` | `ValueError` raised |
| `test_setup_bot_data_sets_repo_in_bot_data` | `ReportHistoryRepository` patched | `application.bot_data["repo"]` is set after call |

---

## Out of Scope

- No new bot commands (`/status`, `/history`, etc.)
- No webhook mode
- No per-user auth or allowlist
- No bot integration tests (PTB network calls)
