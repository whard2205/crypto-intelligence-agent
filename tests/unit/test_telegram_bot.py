import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import Settings
from telegram_bot.main import (
    HELP_TEXT,
    build_bot,
    help_command,
    history_command,
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
    invoked_symbols = {c.args[0]["symbol"] for c in graph.ainvoke.call_args_list}
    assert invoked_symbols == {"BTCUSDT", "ETHUSDT"}


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

    graph.ainvoke.assert_called_once()
    reply_arg = update.message.reply_text.call_args[0][0]
    assert "❌" not in reply_arg


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


async def test_history_command_no_repo_sends_unavailable_message():
    settings = _make_settings()
    graph    = _make_graph()
    update   = _make_update()
    context  = _make_context(settings, graph, repo=None, args=["BTCUSDT"])

    await history_command(update, context)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "⚠️" in reply_text


async def test_history_command_invalid_symbol_sends_error():
    settings = _make_settings()
    graph    = _make_graph()
    repo     = _make_repo()
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=["bad!sym"])

    await history_command(update, context)

    reply_text = update.message.reply_text.call_args[0][0]
    assert "Invalid symbol" in reply_text
    repo.get_latest.assert_not_called()


async def test_history_command_non_digit_limit_uses_default():
    settings = _make_settings()
    graph    = _make_graph()
    repo     = _make_repo()
    update   = _make_update()
    context  = _make_context(settings, graph, repo=repo, args=["BTCUSDT", "abc"])

    await history_command(update, context)

    repo.get_latest.assert_called_once()
    assert repo.get_latest.call_args.kwargs["limit"] == 5
