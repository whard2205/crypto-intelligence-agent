import pytest
from tests.conftest import make_state, make_ohlcv
from graph.aggregator import aggregate_raw, merge_analysis


def _state_with_price():
    state = make_state()
    state["price_data"] = {
        "symbol": "BTCUSDT", "price_usd": 65000.0,
        "change_24h_pct": 2.3, "volume_24h_usd": 28e9,
        "high_24h": 66000.0, "low_24h": 64000.0,
        "ohlcv_24h": make_ohlcv(30), "source": "mock",
    }
    state["news_data"]    = [{"title": "BTC surges", "source": "mock",
                               "published_at": "", "url": ""}]
    state["onchain_data"] = {"network": "bitcoin", "active_addresses_24h": 1_000_000}
    state["social_data"]  = {"post_count": 20, "top_posts": [], "source": "mock"}
    return state


async def test_aggregate_raw_builds_context():
    state = _state_with_price()
    result = await aggregate_raw(state)
    ctx = result["context"]

    assert ctx["symbol"] == "BTCUSDT"
    assert ctx["price_summary"]["price"] == 65000.0
    assert len(ctx["news_items"]) == 1
    assert ctx["news_items"][0]["headline"] == "BTC surges"
    assert ctx["social_summary"]["mention_volume"] == 20
    assert isinstance(ctx["ohlcv_24h"] if "ohlcv_24h" in ctx
                       else ctx["price_summary"]["ohlcv_24h"], list)


async def test_aggregate_raw_returns_error_when_price_missing():
    state = make_state()
    result = await aggregate_raw(state)
    assert "report" in result
    assert "error" in result["report"]
    assert result["report"]["symbol"] == "BTCUSDT"


async def test_aggregate_raw_deduplicates_data_gaps():
    state = _state_with_price()
    state["data_gaps"] = ["news_unavailable", "news_unavailable", "onchain_unavailable"]
    result = await aggregate_raw(state)
    ctx = result["context"]
    assert len(ctx["data_gaps"]) == len(set(ctx["data_gaps"]))


async def test_merge_analysis_combines_outputs():
    state = make_state()
    state["sentiment_analysis"] = {
        "sentiment_score": 0.4, "sentiment_label": "bullish",
        "sentiment_drivers": ["BTC surges"],
    }
    state["market_structure_analysis"] = {
        "bias": "bullish", "rsi": 58.0, "ma_trend": "uptrend",
        "confidence_score": 0.65, "explanation": "CHOCH bullish",
        "swing_highs": [65100.0], "swing_lows": [63900.0],
        "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
        "volume_confirmed": True, "invalidation_level": 63900.0,
        "macd_histogram_slope": 0.002, "momentum_pct": 1.2,
        "ml_probability_1r": None, "ml_probability_2r": None,
    }
    state["risk_analysis"] = {"risk_level": "low", "risk_factors": []}
    result = merge_analysis(state)
    analysis = result["analysis"]

    assert analysis["sentiment_label"] == "bullish"
    assert analysis["market_structure"]["rsi"] == 58.0
    assert analysis["risk_level"] == "low"


async def test_merge_analysis_handles_none_inputs():
    state = make_state()
    state["sentiment_analysis"]        = None
    state["market_structure_analysis"] = None
    state["risk_analysis"]             = None
    result = merge_analysis(state)
    analysis = result["analysis"]
    assert analysis["sentiment_label"] is None
    assert analysis["market_structure"] is None


async def test_aggregate_includes_funding_summary():
    state = _state_with_price()
    state["funding_rate_data"] = {
        "symbol": "BTCUSDT", "funding_rate": 0.00080,
        "funding_time": "2026-05-06T08:00:00Z", "source": "binance",
    }
    result = await aggregate_raw(state)
    ctx = result["context"]
    assert ctx["funding_rate_summary"] is not None
    assert ctx["funding_rate_summary"]["rate"] == pytest.approx(0.00080)
    assert ctx["funding_rate_summary"]["source"] == "binance"
    assert ctx["funding_rate_summary"]["funding_time"] == "2026-05-06T08:00:00Z"


async def test_aggregate_funding_none_when_missing():
    state = _state_with_price()
    # funding_rate_data is already None in make_state() default
    result = await aggregate_raw(state)
    ctx = result["context"]
    assert ctx["funding_rate_summary"] is None
    assert "funding_unavailable" in ctx["data_gaps"]
