import pytest
from unittest.mock import AsyncMock, MagicMock
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
