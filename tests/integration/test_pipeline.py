import pytest
from unittest.mock import AsyncMock
from config.settings import Settings
from data_sources.base import DataSourceAdapter
from graph.pipeline import build_graph


class _MockAdapter(DataSourceAdapter):
    def __init__(self, name: str, payload):
        self.source_name = name
        self._payload = payload

    async def fetch(self, symbol: str):
        return self._payload


def _initial_state(symbol: str = "BTCUSDT") -> dict:
    from graph.state import AgentState
    import uuid, datetime
    return {
        "run_id": str(uuid.uuid4()),
        "symbol": symbol,
        "requested_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "price_data": None,
        "news_data": [],
        "onchain_data": None,
        "social_data": None,
        "context": None,
        "sentiment_analysis": None,
        "market_structure_analysis": None,
        "risk_analysis": None,
        "analysis": None,
        "report": None,
        "data_gaps": [],
        "errors": [],
    }


def _make_price_payload(symbol: str = "BTCUSDT"):
    import math
    base = 65000.0
    n = 60
    candles = []
    for i in range(n):
        trend = (i / n) * base * 0.065
        cycle = base * 0.014 * math.sin(i * 2 * math.pi / 18)
        close = base + trend + cycle
        candles.append({
            "open": round(close - base * 0.003, 2),
            "high": round(close + base * 0.005, 2),
            "low": round(close - base * 0.005, 2),
            "close": round(close, 2),
            "volume": 500 + i * 10,
        })
    return {
        "symbol": symbol,
        "price_usd": candles[-1]["close"],
        "change_24h_pct": 2.3,
        "volume_24h_usd": 28e9,
        "high_24h": 66000.0,
        "low_24h": 64000.0,
        "ohlcv_24h": candles,
        "source": "mock",
    }


@pytest.fixture
def settings_mock():
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


@pytest.fixture
def mock_graph(settings_mock):
    price   = _MockAdapter("mock_price",   _make_price_payload())
    news    = _MockAdapter("mock_news",    [{"title": "BTC rally", "source": "mock",
                                             "published_at": "", "url": ""}])
    onchain = _MockAdapter("mock_onchain", {"network": "bitcoin", "active_addresses_24h": 1_000_000})
    social  = _MockAdapter("mock_social",  {"post_count": 20, "top_posts": [], "source": "mock"})
    return build_graph(settings_mock, price, news, onchain, social)


async def test_full_pipeline_btcusdt(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]

    assert not report.get("error")
    assert report["symbol"] == "BTCUSDT"
    assert report["market_bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= report["confidence_score"] <= 1.0
    assert isinstance(report["key_signals"], list)
    assert len(report["key_signals"]) >= 1
    assert isinstance(report["narrative"], str)
    assert report["llm_used"] is False


async def test_pipeline_returns_error_report_when_price_missing(settings_mock):
    bad_price = _MockAdapter("mock_price", None)
    news      = _MockAdapter("mock_news",    [])
    onchain   = _MockAdapter("mock_onchain", {})
    social    = _MockAdapter("mock_social",  {})
    graph = build_graph(settings_mock, bad_price, news, onchain, social)

    result = await graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]
    assert "error" in report
    assert report["symbol"] == "BTCUSDT"


async def test_pipeline_continues_when_social_missing(settings_mock):
    price   = _MockAdapter("mock_price",   _make_price_payload())
    news    = _MockAdapter("mock_news",    [{"title": "BTC rally", "source": "mock",
                                             "published_at": "", "url": ""}])
    onchain = _MockAdapter("mock_onchain", {"network": "bitcoin", "active_addresses_24h": 1_000_000})
    social  = _MockAdapter("mock_social",  None)
    graph = build_graph(settings_mock, price, news, onchain, social)

    result = await graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]
    assert not report.get("error")
    assert "social_unavailable" in report.get("data_gaps", [])


async def test_pipeline_full_report_structure(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]

    required_keys = {
        "symbol", "market_bias", "confidence_score",
        "key_signals", "narrative", "llm_used",
        "generated_at", "data_gaps",
    }
    assert required_keys.issubset(report.keys())
    assert isinstance(report["data_gaps"], list)
    assert isinstance(report["generated_at"], str)
