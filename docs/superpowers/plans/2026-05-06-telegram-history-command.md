# Telegram /history Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/history` Telegram command that shows compact summaries of the last N stored reports for one or all watched symbols, reading directly from `ReportHistoryRepository`.

**Architecture:** Two-file change — (1) add `format_history_summary` formatter to `publishers/telegram_publisher.py` alongside the existing `format_intelligence_report`, (2) add `history_command` handler to `telegram_bot/main.py` following the exact pattern of `report_command`. No new files except the formatter test file.

**Tech Stack:** python-telegram-bot, aiosqlite (via existing `ReportHistoryRepository`), `unittest.mock` for tests.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `publishers/telegram_publisher.py` | Modify | Add `_utc_to_local_short` helper + `format_history_summary` function |
| `telegram_bot/main.py` | Modify | Add `DEFAULT_HISTORY_LIMIT`, `MAX_HISTORY_LIMIT` constants; add `history_command` handler; update `HELP_TEXT`; update import; register handler in `build_bot` |
| `tests/unit/test_history_formatter.py` | Create | 6 unit tests for `format_history_summary` |
| `tests/unit/test_telegram_bot.py` | Modify | Add 6 tests for `history_command`; update import block |

---

## Task 1: `format_history_summary` formatter (TDD)

**Files:**
- Create: `tests/unit/test_history_formatter.py`
- Modify: `publishers/telegram_publisher.py`

### Step 1: Write failing tests

Create `tests/unit/test_history_formatter.py` with this exact content:

```python
import pytest
from publishers.telegram_publisher import format_history_summary


def _make_record(
    bias: str = "bullish",
    conf: float | None = 0.82,
    signals: list | None = None,
    generated_at: str = "2026-05-06T07:30:00+00:00",
) -> dict:
    return {
        "symbol": "BTCUSDT",
        "market_bias": bias,
        "confidence_score": conf,
        "key_signals": signals if signals is not None else [],
        "generated_at": generated_at,
    }


def test_single_entry_bias_changed():
    record = _make_record(signals=["Bias changed: bearish → bullish"])
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    assert "↗ bias berubah" in result


def test_single_entry_no_bias_change():
    record = _make_record()
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    # last column is "—" when no bias change
    lines = [l for l in result.splitlines() if "📅" in l]
    assert lines[0].endswith("—")


def test_multiple_entries_rendered():
    records = [
        _make_record(generated_at="2026-05-06T07:30:00+00:00"),
        _make_record(generated_at="2026-05-06T03:00:00+00:00"),
        _make_record(generated_at="2026-05-05T15:15:00+00:00"),
    ]
    result = format_history_summary("BTCUSDT", records, "Asia/Jakarta")
    assert result.count("📅") == 3


def test_empty_records_returns_no_history_message():
    result = format_history_summary("BTCUSDT", [], "Asia/Jakarta")
    assert "tidak ada history" in result.lower()


def test_confidence_none_does_not_crash():
    record = _make_record(conf=None)
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    assert "—" in result  # conf shown as "—" when None


def test_timestamp_formatted_to_timezone():
    # UTC 00:00:00 → WIB (UTC+7) = 07:00
    record = _make_record(generated_at="2026-05-06T00:00:00+00:00")
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    assert "07:00" in result
```

- [ ] **Step 2: Run to confirm all 6 fail**

```
uv run pytest tests/unit/test_history_formatter.py -v
```

Expected: 6 × `FAILED` with `ImportError` or `AttributeError` (function not yet defined).

- [ ] **Step 3: Add `_utc_to_local_short` and `format_history_summary` to `publishers/telegram_publisher.py`**

After the existing `_utc_to_local` function (after line 27), add:

```python
def _utc_to_local_short(iso_str: str, tz_name: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone(ZoneInfo(tz_name))
        return local_dt.strftime("%d %b %H:%M")
    except Exception:
        return iso_str
```

After the existing `format_intelligence_report` function, add the new public formatter:

```python
def format_history_summary(symbol: str, records: list[dict], tz_name: str) -> str:
    """Compact multi-line history summary for one symbol. Returns HTML for parse_mode='HTML'."""
    if not records:
        return f"<i>Tidak ada history untuk {_html(symbol)}.</i>"

    lines = [f"📊 <b>{_html(symbol)}</b> — {len(records)} laporan terakhir", ""]

    for r in records:
        ts    = _utc_to_local_short(r.get("generated_at", ""), tz_name)
        bias  = r.get("market_bias", "neutral")
        emoji = _BIAS_EMOJI.get(bias, "🟡")
        conf  = r.get("confidence_score")
        conf_s = f"{conf:.2f}" if conf is not None else "—"

        signals      = r.get("key_signals") or []
        bias_changed = any(str(s).startswith("Bias changed:") for s in signals)
        change_str   = "↗ bias berubah" if bias_changed else "—"

        lines.append(f"📅 {ts} | {emoji} {bias.capitalize()} | conf: {conf_s} | {change_str}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests — confirm all 6 pass**

```
uv run pytest tests/unit/test_history_formatter.py -v
```

Expected: 6 × `PASSED`.

- [ ] **Step 5: Run full suite to check no regressions**

```
uv run pytest -q
```

Expected: all tests pass (currently 154).

- [ ] **Step 6: Commit**

```
git add publishers/telegram_publisher.py tests/unit/test_history_formatter.py
git commit -m "feat: add format_history_summary to telegram_publisher"
```

---

## Task 2: `history_command` handler (TDD)

**Files:**
- Modify: `tests/unit/test_telegram_bot.py`
- Modify: `telegram_bot/main.py`

### Step 1: Add failing tests to `tests/unit/test_telegram_bot.py`

**a. Update the import block at the top of the file** (lines 5–12). Add `history_command` to the import:

```python
from telegram_bot.main import (
    HELP_TEXT,
    build_bot,
    help_command,
    history_command,
    report_command,
    setup_bot_data,
    start_command,
)
```

**b. Append the 6 new tests at the end of `tests/unit/test_telegram_bot.py`:**

```python
# ---------------------------------------------------------------------------
# history_command
# ---------------------------------------------------------------------------

async def test_history_command_no_args_calls_get_latest_for_all_symbols():
    settings = _make_settings("BTCUSDT,ETHUSDT")
    graph    = _make_graph()
    repo     = _make_repo()
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=[])

    await history_command(update, context)

    assert repo.get_latest.call_count == 2
    called_symbols = {c.args[0] for c in repo.get_latest.call_args_list}
    assert called_symbols == {"BTCUSDT", "ETHUSDT"}


async def test_history_command_single_symbol_calls_get_latest_once():
    settings = _make_settings()
    graph    = _make_graph()
    repo     = _make_repo()
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=["BTCUSDT"])

    await history_command(update, context)

    repo.get_latest.assert_called_once()
    assert repo.get_latest.call_args.args[0] == "BTCUSDT"


async def test_history_command_custom_limit_passed_to_repo():
    settings = _make_settings()
    graph    = _make_graph()
    repo     = _make_repo()
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=["BTCUSDT", "7"])

    await history_command(update, context)

    repo.get_latest.assert_called_once()
    assert repo.get_latest.call_args.kwargs["limit"] == 7


async def test_history_command_limit_capped_at_10():
    settings = _make_settings()
    graph    = _make_graph()
    repo     = _make_repo()
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=["BTCUSDT", "20"])

    await history_command(update, context)

    repo.get_latest.assert_called_once()
    assert repo.get_latest.call_args.kwargs["limit"] == 10


async def test_history_command_empty_result_sends_no_history_message():
    settings = _make_settings()
    graph    = _make_graph()
    repo     = _make_repo()  # get_latest returns [] by default
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=["BTCUSDT"])

    await history_command(update, context)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "tidak ada history" in reply_text.lower()


async def test_history_command_repo_error_sends_error_reply():
    from unittest.mock import AsyncMock as _AM
    settings = _make_settings()
    graph    = _make_graph()
    repo     = _make_repo()
    repo.get_latest = _AM(side_effect=RuntimeError("db error"))
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=["BTCUSDT"])

    await history_command(update, context)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "❌" in reply_text
```

- [ ] **Step 2: Run failing tests — confirm 6 fail**

```
uv run pytest tests/unit/test_telegram_bot.py -v -k "history"
```

Expected: 6 × `FAILED` with `ImportError` (function not defined yet).

- [ ] **Step 3: Implement in `telegram_bot/main.py`**

**a. Update the import from `telegram_publisher` at line 14:**

Old:
```python
from publishers.telegram_publisher import format_intelligence_report
```

New:
```python
from publishers.telegram_publisher import format_history_summary, format_intelligence_report
```

**b. After the `_SYMBOL_RE` line (line 19), add two module-level constants:**

```python
_DEFAULT_HISTORY_LIMIT = 5
_MAX_HISTORY_LIMIT     = 10
```

**c. Update `HELP_TEXT` — add history lines to the Commands section.**

Old Commands section (inside `HELP_TEXT`):
```python
    "<b>Commands:</b>\n"
    "/help — Show this message\n"
    "/report — Generate reports for all watched symbols\n"
    "/report &lt;SYMBOL&gt; — Generate report for one symbol\n\n"
```

New:
```python
    "<b>Commands:</b>\n"
    "/help — Show this message\n"
    "/report — Generate reports for all watched symbols\n"
    "/report &lt;SYMBOL&gt; — Generate report for one symbol\n"
    "/history — Show last 5 reports for all watched symbols\n"
    "/history &lt;SYMBOL&gt; — Show last 5 reports for one symbol\n"
    "/history &lt;SYMBOL&gt; &lt;N&gt; — Show last N reports (max 10)\n\n"
```

**d. Add the `history_command` function after `report_command` (before the `_post_init` function):**

```python
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings                   = context.bot_data["settings"]
    repo: ReportHistoryRepository | None = context.bot_data.get("repo")

    args = list(context.args or [])

    if args:
        symbol = args[0].upper()
        if not _SYMBOL_RE.match(symbol):
            await update.message.reply_text(
                f"❌ Invalid symbol: <code>{symbol}</code>\n"
                "Use uppercase letters only, e.g. <code>/history BTCUSDT</code>",
                parse_mode="HTML",
            )
            return
        symbols = [symbol]

        limit = _DEFAULT_HISTORY_LIMIT
        if len(args) >= 2:
            try:
                limit = int(args[1])
            except (ValueError, TypeError):
                limit = _DEFAULT_HISTORY_LIMIT
        limit = min(max(limit, 1), _MAX_HISTORY_LIMIT)
    else:
        symbols = [s.strip() for s in settings.WATCH_SYMBOLS.split(",") if s.strip()]
        limit   = _DEFAULT_HISTORY_LIMIT

    for symbol in symbols:
        try:
            records = await repo.get_latest(symbol, limit=limit)
            msg = format_history_summary(symbol, records, settings.DISPLAY_TIMEZONE)
            await update.message.reply_text(msg, parse_mode="HTML")
        except Exception as exc:
            logger.exception("Failed to fetch history for %s", symbol)
            await update.message.reply_text(
                f"❌ Failed to fetch history for <code>{symbol}</code>: {exc}",
                parse_mode="HTML",
            )
```

**e. Register the handler in `build_bot` — add after the `report` handler (line 138):**

Old:
```python
    app.add_handler(CommandHandler("report", report_command))
```

New:
```python
    app.add_handler(CommandHandler("report",  report_command))
    app.add_handler(CommandHandler("history", history_command))
```

- [ ] **Step 4: Run the 6 new tests — confirm all pass**

```
uv run pytest tests/unit/test_telegram_bot.py -v -k "history"
```

Expected: 6 × `PASSED`.

- [ ] **Step 5: Run full suite — confirm no regressions**

```
uv run pytest -q
```

Expected: all tests pass (160 total: 154 existing + 6 formatter + 6 bot = 166).

- [ ] **Step 6: Commit**

```
git add telegram_bot/main.py tests/unit/test_telegram_bot.py
git commit -m "feat: add /history Telegram command with compact report summary"
```

---

## Telegram Message Length Analysis

| Scenario | Chars per message |
|---|---|
| 5 entries (default) | ~450 chars |
| 10 entries (max) | ~900 chars |
| Telegram hard limit | 4096 chars |

No message truncation needed. Even the pathological case (10 entries with long bias-changed strings) stays well under 1200 chars.

---

## Symbol Validation Notes

- Reuses `_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{2,19}$")` — already defined at module level.
- Invalid symbol → early return with error reply, identical to `/report` behavior.
- No guard needed for `repo is None` path: `setup_bot_data` always creates and stores a repo. The `get_latest` call inside the `try/except` covers any unexpected failure.
