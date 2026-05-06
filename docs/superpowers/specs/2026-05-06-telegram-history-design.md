# Phase 8C — Telegram /history Command

**Date:** 2026-05-06
**Status:** Approved, pending implementation

---

## Overview

Add a `/history` command to the existing Telegram bot. It pulls the last N reports for one or all watched symbols from `ReportHistoryRepository` and sends a compact summary per symbol — one line per entry showing timestamp, bias, confidence, and whether a bias change was detected.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Format per entry | Compact single-line summary | `/history` is a quick-scan command; full reports available via `/report` |
| Formatter location | `publishers/telegram_publisher.py` | Consistent with existing `format_intelligence_report`; reuses `_BIAS_EMOJI`; testable independently |
| No-args behavior | Show all `WATCH_SYMBOLS`, one message per symbol | Consistent with `/report` no-args behavior |
| Default limit | 5 | Enough to see trend; fits in one message well under 4096 chars |
| Max limit | 10 (silent cap) | Prevents chat flood; `get_latest` already supports `limit` param |
| N > max behavior | Silent cap to 10, no error reply | YAGNI; edge case not worth user-facing warning |
| Invalid N | Fall back to default 5 | Same rationale |
| Bias change indicator | Check `key_signals` for `"Bias changed:"` prefix | Reuses Phase 8A signal already stored in reports |

---

## Files

### New files

| File | Purpose |
|---|---|
| `tests/unit/test_history_formatter.py` | ~6 unit tests for `format_history_summary` |

### Modified files

| File | Change |
|---|---|
| `publishers/telegram_publisher.py` | Add `format_history_summary(symbol, records, tz_name)` |
| `telegram_bot/main.py` | Add `history_command`, register handler, update `HELP_TEXT` |
| `tests/unit/test_telegram_bot.py` | Add ~6 tests for `history_command` |

---

## Output Format

One message per symbol:

```
📊 <b>BTCUSDT</b> — 5 laporan terakhir

📅 06 Mei 14:30 | 🟢 Bullish  | conf: 0.82 | ↗ bias berubah
📅 06 Mei 10:00 | 🔴 Bearish  | conf: 0.65 | —
📅 05 Mei 22:15 | 🔴 Bearish  | conf: 0.71 | —
📅 05 Mei 18:00 | 🟡 Neutral  | conf: 0.55 | —
📅 05 Mei 14:00 | 🔴 Bearish  | conf: 0.68 | —
```

Empty result:

```
<i>Tidak ada history untuk BTCUSDT.</i>
```

Implementation notes:
- Reuse `_BIAS_EMOJI` from `telegram_publisher.py`
- `↗ bias berubah` shown when any `key_signals` entry starts with `"Bias changed:"`
- Timestamp from `generated_at`, formatted to `settings.DISPLAY_TIMEZONE`
- `confidence_score` shown as 2 decimal places; fallback `"—"` if None
- 5 entries × ~80 chars ≈ 400 chars — well under Telegram's 4096 char limit

---

## `format_history_summary` Signature

```python
# publishers/telegram_publisher.py
def format_history_summary(symbol: str, records: list[dict], tz_name: str) -> str:
    ...
```

Returns HTML string ready for `parse_mode="HTML"`. Returns empty-history message if `records` is empty.

---

## Command Parsing

| Input | Behavior |
|---|---|
| `/history` | All `WATCH_SYMBOLS`, limit=5 |
| `/history BTCUSDT` | Single symbol, limit=5 |
| `/history BTCUSDT 7` | Single symbol, limit=7 |
| `/history BTCUSDT 20` | Single symbol, limit=10 (silent cap) |
| `/history bad!sym` | Invalid symbol → error reply (same regex as `/report`) |
| `/history BTCUSDT abc` | Non-digit N → use default 5 |

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `TELEGRAM_BOT_ENABLED=false` | Bot not started; command unreachable |
| Empty result from repo | Reply: `<i>Tidak ada history untuk SYMBOL.</i>` |
| `repo.get_latest` raises | Log exception + reply `❌ Failed to fetch history for SYMBOL: {exc}` |
| Invalid symbol | Reply error same as `/report` invalid symbol handling |

---

## `HELP_TEXT` Update

Add to commands section:
```
/history — Show last 5 reports for all watched symbols
/history &lt;SYMBOL&gt; — Show last 5 reports for one symbol
/history &lt;SYMBOL&gt; &lt;N&gt; — Show last N reports (max 10)
```

---

## Test Plan

### `tests/unit/test_history_formatter.py` (~6 tests)

| Test | Scenario | Assertion |
|---|---|---|
| `test_single_entry_bias_changed` | record with `"Bias changed:"` in key_signals | `↗ bias berubah` in output |
| `test_single_entry_no_bias_change` | record without bias change signal | `—` in output |
| `test_multiple_entries_rendered` | 3 records | all 3 timestamps appear in output |
| `test_empty_records_returns_no_history_message` | empty list | "tidak ada history" (case-insensitive) in output |
| `test_confidence_none_does_not_crash` | record with `confidence_score=None` | `—` in output, no exception |
| `test_timestamp_formatted_to_timezone` | `generated_at` in UTC, `tz_name="Asia/Jakarta"` | output contains WIB offset or Jakarta time |

### `tests/unit/test_telegram_bot.py` (add ~6 tests)

| Test | Scenario | Assertion |
|---|---|---|
| `test_history_command_no_args_calls_get_latest_for_all_symbols` | no args, `WATCH_SYMBOLS="BTCUSDT,ETHUSDT"` | `repo.get_latest` called twice, once per symbol |
| `test_history_command_single_symbol_calls_get_latest_once` | args=`["BTCUSDT"]` | `repo.get_latest` called once with `symbol="BTCUSDT"` |
| `test_history_command_custom_limit_passed_to_repo` | args=`["BTCUSDT", "7"]` | `repo.get_latest` called with `limit=7` |
| `test_history_command_limit_capped_at_10` | args=`["BTCUSDT", "20"]` | `repo.get_latest` called with `limit=10` |
| `test_history_command_empty_result_sends_no_history_message` | `repo.get_latest` returns `[]` | reply contains "tidak ada history" (case-insensitive) |
| `test_history_command_repo_error_sends_error_reply` | `repo.get_latest` raises `RuntimeError` | reply contains `❌` |

---

## Out of Scope

- Pagination beyond max 10 entries
- Filter by date range
- `/history` without bot running (no-bot path)
- Per-user history isolation
