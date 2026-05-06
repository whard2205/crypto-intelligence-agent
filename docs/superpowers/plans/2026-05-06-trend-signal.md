# Phase 8A — Historical Trend Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-processing enrichment step that compares `market_bias` to the previous saved report for the same symbol and appends a `"Bias changed: {prev} → {current} since last report"` signal to `key_signals` when the bias has changed.

**Architecture:** A standalone async helper `inject_trend_signal(report, repo)` in `graph/trend.py` does all the work — it fetches the last saved report for the symbol, compares biases, and returns a new dict with the signal appended (or the original dict unchanged). Both `scheduler/job.py` and `telegram_bot/main.py` call this helper after `graph.ainvoke()` returns, before `repo.save`. The pipeline itself is not touched.

**Tech Stack:** Python asyncio, `unittest.mock.AsyncMock`, existing `ReportHistoryRepository` (`get_latest(symbol, limit=1)`), `pytest` with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` decorator needed; run via `uv run pytest`).

**Spec:** `docs/superpowers/specs/2026-05-06-trend-signal-design.md`

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `graph/trend.py` | `inject_trend_signal(report, repo)` — enrichment helper |
| `tests/unit/test_trend_signal.py` | 7 unit tests for all enrichment paths |

### Modified files
| File | Change |
|---|---|
| `scheduler/job.py` | Call `inject_trend_signal` in `_run_single` after pipeline success, before `repo.save`; add import |
| `tests/unit/test_scheduler_job.py` | Add `repo.get_latest = AsyncMock(return_value=[])` to `_make_repo()` so existing tests don't break |
| `telegram_bot/main.py` | Fix missing `funding_rate_data` in `_make_initial_state`; call `inject_trend_signal` in `report_command` |

---

## Task 1: `inject_trend_signal` helper + unit tests

**Files:**
- Create: `graph/trend.py`
- Create: `tests/unit/test_trend_signal.py`

- [ ] **Step 1: Write all 7 failing tests**

Create `tests/unit/test_trend_signal.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from graph.trend import inject_trend_signal


def _make_repo(history: list[dict] | None = None, side_effect=None) -> MagicMock:
    repo = MagicMock()
    if side_effect is not None:
        repo.get_latest = AsyncMock(side_effect=side_effect)
    else:
        repo.get_latest = AsyncMock(return_value=history if history is not None else [])
    return repo


# ---------------------------------------------------------------------------
# Bias changed → signal appended
# ---------------------------------------------------------------------------

async def test_bias_changed_appends_signal():
    report = {
        "symbol": "BTCUSDT",
        "market_bias": "bullish",
        "key_signals": ["RSI oversold"],
    }
    repo = _make_repo(history=[{"market_bias": "bearish"}])

    result = await inject_trend_signal(report, repo)

    assert "Bias changed: bearish → bullish since last report" in result["key_signals"]


# ---------------------------------------------------------------------------
# Bias unchanged → no signal
# ---------------------------------------------------------------------------

async def test_bias_unchanged_no_signal():
    report = {
        "symbol": "BTCUSDT",
        "market_bias": "bullish",
        "key_signals": ["RSI oversold"],
    }
    repo = _make_repo(history=[{"market_bias": "bullish"}])

    result = await inject_trend_signal(report, repo)

    assert not any(s.startswith("Bias changed:") for s in result["key_signals"])


# ---------------------------------------------------------------------------
# No history → no signal
# ---------------------------------------------------------------------------

async def test_no_history_no_signal():
    report = {
        "symbol": "BTCUSDT",
        "market_bias": "bullish",
        "key_signals": [],
    }
    repo = _make_repo(history=[])

    result = await inject_trend_signal(report, repo)

    assert result["key_signals"] == []


# ---------------------------------------------------------------------------
# Repo error → return unchanged, no exception
# ---------------------------------------------------------------------------

async def test_repo_error_returns_report_unchanged():
    report = {
        "symbol": "BTCUSDT",
        "market_bias": "bullish",
        "key_signals": [],
    }
    repo = _make_repo(side_effect=Exception("db error"))

    result = await inject_trend_signal(report, repo)

    assert result is report


# ---------------------------------------------------------------------------
# Error report → skip entirely (get_latest not called)
# ---------------------------------------------------------------------------

async def test_error_report_skipped():
    report = {
        "symbol": "BTCUSDT",
        "market_bias": None,
        "error": "Pipeline failed",
        "key_signals": [],
    }
    repo = _make_repo()

    result = await inject_trend_signal(report, repo)

    repo.get_latest.assert_not_called()
    assert result is report


# ---------------------------------------------------------------------------
# Does not mutate input dict
# ---------------------------------------------------------------------------

async def test_does_not_mutate_input():
    original_signals = ["RSI oversold"]
    report = {
        "symbol": "BTCUSDT",
        "market_bias": "bullish",
        "key_signals": original_signals,
    }
    repo = _make_repo(history=[{"market_bias": "bearish"}])

    result = await inject_trend_signal(report, repo)

    assert result is not report
    assert report["key_signals"] is original_signals
    assert "Bias changed: bearish → bullish since last report" not in original_signals


# ---------------------------------------------------------------------------
# Duplicate protection: already has "Bias changed:" → skip (get_latest not called)
# ---------------------------------------------------------------------------

async def test_does_not_append_duplicate_trend_signal():
    existing_signal = "Bias changed: bearish → bullish since last report"
    report = {
        "symbol": "BTCUSDT",
        "market_bias": "bullish",
        "key_signals": ["RSI oversold", existing_signal],
    }
    repo = _make_repo()

    result = await inject_trend_signal(report, repo)

    repo.get_latest.assert_not_called()
    assert result["key_signals"].count(existing_signal) == 1
```

- [ ] **Step 2: Run to confirm all 7 tests fail**

```
uv run pytest tests/unit/test_trend_signal.py -v
```

Expected: all 7 FAIL — `ModuleNotFoundError: No module named 'graph.trend'`

- [ ] **Step 3: Create `graph/trend.py`**

```python
from __future__ import annotations
import logging

from storage.report_history import ReportHistoryRepository

logger = logging.getLogger(__name__)


async def inject_trend_signal(
    report: dict,
    repo: ReportHistoryRepository,
) -> dict:
    if report.get("error"):
        return report

    symbol       = report.get("symbol", "")
    current_bias = report.get("market_bias")

    if not symbol or not current_bias:
        return report

    key_signals = list(report.get("key_signals") or [])

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

- [ ] **Step 4: Run tests to confirm all 7 pass**

```
uv run pytest tests/unit/test_trend_signal.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```
git add graph/trend.py tests/unit/test_trend_signal.py
git commit -m "feat: add inject_trend_signal enrichment helper"
```

---

## Task 2: Wire into `scheduler/job.py`

**Files:**
- Modify: `scheduler/job.py`
- Modify: `tests/unit/test_scheduler_job.py`

After this task, `_run_single` calls `inject_trend_signal` between the pipeline success and `repo.save`. The existing 9 scheduler tests must continue to pass — the only required change is adding `get_latest` to the mock repo so the helper doesn't error when called.

- [ ] **Step 1: Update `_make_repo()` in `tests/unit/test_scheduler_job.py`**

The `inject_trend_signal` helper calls `repo.get_latest(symbol, limit=1)`. The existing `_make_repo()` only mocks `repo.save`. Add `get_latest` returning an empty list (no history → no signal appended → assertions unchanged):

Find the current `_make_repo`:
```python
def _make_repo():
    repo = MagicMock()
    repo.save = AsyncMock()
    return repo
```

Replace with:
```python
def _make_repo():
    repo = MagicMock()
    repo.save = AsyncMock()
    repo.get_latest = AsyncMock(return_value=[])
    return repo
```

- [ ] **Step 2: Run scheduler tests to confirm all 9 still pass before touching `job.py`**

```
uv run pytest tests/unit/test_scheduler_job.py -v
```

Expected: 9 PASSED (the `get_latest` mock has no effect yet since `job.py` doesn't call it yet — confirming the mock change itself doesn't break anything)

- [ ] **Step 3: Update `scheduler/job.py`**

Add the import at the top (after existing imports):
```python
from graph.trend import inject_trend_signal
```

Replace the `_run_single` function body so the enrichment step runs after pipeline success, before `repo.save`. The full updated `_run_single`:

```python
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
        report = await inject_trend_signal(report, repo)

    if report is not None and not report.get("error"):
        try:
            await repo.save(report)
        except Exception as exc:
            logger.error("Failed to save report for %s to history: %s", symbol, exc)

    try:
        await publisher.publish(report)
    except Exception:
        logger.error("Telegram send failed for %s", symbol)
```

- [ ] **Step 4: Run scheduler tests to confirm all 9 still pass**

```
uv run pytest tests/unit/test_scheduler_job.py -v
```

Expected: 9 PASSED. With `get_latest` returning `[]`, `inject_trend_signal` adds no signal and returns the report unchanged — all existing assertions hold.

- [ ] **Step 5: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```
git add scheduler/job.py tests/unit/test_scheduler_job.py
git commit -m "feat: wire inject_trend_signal into scheduler _run_single"
```

---

## Task 3: Wire into `telegram_bot/main.py` + fix `_make_initial_state`

**Files:**
- Modify: `telegram_bot/main.py`

Two changes in this file:
1. Fix `_make_initial_state` — it is missing `"funding_rate_data": None` (already present in `scheduler/job.py`'s `_invoke_pipeline`).
2. Call `inject_trend_signal` in `report_command` after `report = result["report"]` and before `repo.save`.

`repo` can be `None` in the bot if `_post_init` hasn't run yet, so both the enrichment and save stay inside the `if repo:` guard.

- [ ] **Step 1: Update `telegram_bot/main.py`**

Add the import at the top (after existing imports):
```python
from graph.trend import inject_trend_signal
```

Fix `_make_initial_state` — add the missing `"funding_rate_data": None` field:
```python
def _make_initial_state(symbol: str) -> dict:
    return {
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
```

Update `report_command` — replace the `if repo and not report.get("error"):` block so enrichment runs before save:

Find the current block inside the `for symbol in symbols:` loop (after `report = result["report"]`):
```python
            if repo and not report.get("error"):
                try:
                    await repo.save(report)
                except Exception:
                    logger.exception("Failed to save report for %s to history", symbol)
```

Replace with:
```python
            if repo:
                report = await inject_trend_signal(report, repo)
                if not report.get("error"):
                    try:
                        await repo.save(report)
                    except Exception:
                        logger.exception("Failed to save report for %s to history", symbol)
```

- [ ] **Step 2: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 3: Run full test suite**

```
uv run pytest tests/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 4: Commit**

```
git add telegram_bot/main.py
git commit -m "feat: wire inject_trend_signal into telegram bot report_command; fix missing funding_rate_data in initial state"
```

- [ ] **Step 5: Push to GitHub**

```
git push origin main
```
