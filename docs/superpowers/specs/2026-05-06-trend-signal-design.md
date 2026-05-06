# Phase 8A — Historical Trend Signal

**Date:** 2026-05-06
**Status:** Approved, pending implementation

---

## Overview

Add a post-processing enrichment step that compares the current report's `market_bias` to the previous report for the same symbol stored in SQLite. When the bias has changed, the signal `"Bias changed: {prev} → {current} since last report"` is appended to `key_signals`. The pipeline itself remains untouched — enrichment happens after `graph.ainvoke()` returns, before saving and publishing.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Enrichment placement | Post-processing, outside pipeline | Pipeline stays pure and testable; no new state fields needed |
| Where signal appears | Telegram only (scheduled + bot commands) | API `/report` endpoint is for real-time analysis; trend context belongs in push notifications |
| Implementation | Shared helper `inject_trend_signal` in `graph/trend.py` | Single source of truth; both scheduler job and bot handler call the same function |
| Error handling | Log warning, return report unchanged | Trend signal is supplementary; never block report delivery |
| Signal text | `"Bias changed: {prev} → {current} since last report"` | Clear, concise; matches user's stated format |

---

## Files

### New files

| File | Purpose |
|---|---|
| `graph/trend.py` | `inject_trend_signal(report, repo)` — enrichment helper |
| `tests/unit/test_trend_signal.py` | Unit tests for all enrichment paths |

### Modified files

| File | Change |
|---|---|
| `scheduler/job.py` | Call `inject_trend_signal` in `_run_single` after successful pipeline run |
| `telegram_bot/main.py` | Call `inject_trend_signal` in `report_command` after successful pipeline run |

---

## `inject_trend_signal` Logic

```python
# graph/trend.py
async def inject_trend_signal(
    report: dict,
    repo: ReportHistoryRepository,
) -> dict:
    # Skip error reports entirely
    if report.get("error"):
        return report

    symbol       = report.get("symbol", "")
    current_bias = report.get("market_bias")

    if not symbol or not current_bias:
        return report

    key_signals = list(report.get("key_signals") or [])

    # Duplicate protection: skip if a trend signal is already present
    if any(s.startswith("Bias changed:") for s in key_signals):
        return report

    try:
        history = await repo.get_latest(symbol, limit=1)
    except Exception as exc:
        logger.warning("Failed to fetch history for trend signal (%s): %s", symbol, exc)
        return report

    if not history:
        return report

    previous_bias = history[0].get("market_bias")
    if previous_bias and previous_bias != current_bias:
        signal = f"Bias changed: {previous_bias} → {current_bias} since last report"
        report = {**report, "key_signals": key_signals + [signal]}

    return report
```

**Key behaviors:**
- Returns a new dict (does not mutate the input)
- Only appends signal when bias is **different** from previous; identical bias → no signal
- Duplicate protection: if a `"Bias changed:"` signal already exists, returns unchanged (idempotent)
- `repo.get_latest` failure → log WARNING, return unchanged (never raises)
- Error reports skipped entirely

---

## Call Sites

### `scheduler/job.py` — `_run_single`

Insert after `report = await _invoke_pipeline(graph, symbol)` and before `repo.save`:

```python
report = await inject_trend_signal(report, repo)
```

Full updated success path in `_run_single`:
```python
for attempt in (1, 2):
    try:
        report = await _invoke_pipeline(graph, symbol)
        break
    except Exception as exc:
        ...

# Enrich with trend signal before saving/publishing
if report is not None and not report.get("error"):
    report = await inject_trend_signal(report, repo)

if report is not None and not report.get("error"):
    try:
        await repo.save(report)
    except Exception as exc:
        logger.error(...)
```

### `telegram_bot/main.py` — `report_command`

Insert after `report = result["report"]` and before `repo.save`:

```python
report = await inject_trend_signal(report, repo)
```

---

## Test Plan

### `tests/unit/test_trend_signal.py`

All tests use `AsyncMock` for `repo.get_latest`. No real database.

| Test | Scenario | Assertion |
|---|---|---|
| `test_bias_changed_appends_signal` | previous=bearish, current=bullish | "Bias changed: bearish → bullish since last report" in key_signals |
| `test_bias_unchanged_no_signal` | previous=bullish, current=bullish | no "Bias changed" in key_signals |
| `test_no_history_no_signal` | `get_latest` returns `[]` | key_signals unchanged |
| `test_repo_error_returns_report_unchanged` | `get_latest` raises | no exception; report returned unchanged |
| `test_error_report_skipped` | report has `error` key | `get_latest` not called; report returned unchanged |
| `test_does_not_mutate_input` | bias changed | original report dict unchanged; returned new dict |

---

## Out of Scope

- Trend signal in API `/report` endpoint
- Count of consecutive reports with same bias ("bullish for 3 reports")
- Direction arrow emoji in signal text
- Storing trend metadata in the report DB
