import pytest
from config.settings import Settings
from agents.supervisor import make_supervisor
from tests.conftest import make_state


def _make_settings() -> Settings:
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


def _state_with_context(funding_rate_summary) -> dict:
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {"price": 65000.0, "change_24h_pct": 2.3,
                          "volume_24h": 28e9, "high_24h": 66000.0,
                          "low_24h": 64000.0, "ohlcv_24h": []},
        "news_items": [], "onchain_summary": {},
        "social_summary": {}, "data_gaps": [],
        "price_source": "binance", "news_source": "rss",
        "funding_rate_summary": funding_rate_summary,
    }
    state["analysis"] = {
        "sentiment_score": 0.1, "sentiment_label": "neutral",
        "sentiment_drivers": [],
        "market_structure": {
            "bias": "neutral", "rsi": 52.0, "ma_trend": "sideways",
            "confidence_score": 0.20, "explanation": "neutral",
            "swing_highs": [], "swing_lows": [], "liquidity_sweeps": [],
            "order_blocks": [], "bos_choch": [], "volume_confirmed": False,
            "invalidation_level": None, "macd_histogram_slope": 0.0,
            "momentum_pct": 0.0, "ml_probability_1r": None, "ml_probability_2r": None,
        },
        "risk_level": "low", "risk_factors": ["No significant risk factors detected"],
    }
    return state


async def test_funding_signal_in_key_signals_when_moderate():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": +0.00080, "funding_time": "", "source": "binance"}
    ))
    signals = result["report"]["key_signals"]
    assert any("Funding rate" in s for s in signals)


async def test_neutral_funding_not_in_key_signals():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": +0.00010, "funding_time": "", "source": "binance"}
    ))
    signals = result["report"]["key_signals"]
    assert not any("Funding rate" in s for s in signals)


async def test_funding_source_binance():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": 0.00010, "funding_time": "", "source": "binance"}
    ))
    assert result["report"]["funding_source"] == "binance"


async def test_funding_source_mock():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": 0.00080, "funding_time": "", "source": "mock"}
    ))
    assert result["report"]["funding_source"] == "mock"


async def test_funding_source_unavailable_when_summary_is_none():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(None))
    assert result["report"]["funding_source"] == "unavailable"
