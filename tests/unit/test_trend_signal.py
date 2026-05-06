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
