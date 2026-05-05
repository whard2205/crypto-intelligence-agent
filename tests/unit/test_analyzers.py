import pytest
from config.settings import Settings
from tests.conftest import make_state, make_ohlcv


def _state_with_context(news_headlines=None, price_change=2.0, ohlcv=None):
    candles = ohlcv if ohlcv is not None else make_ohlcv(40)
    state = make_state()
    state["context"] = {
        "symbol":   "BTCUSDT",
        "price_summary": {
            "price": 65000.0, "change_24h_pct": price_change,
            "volume_24h": 28e9, "high_24h": 66000.0, "low_24h": 64000.0,
            "ohlcv_24h": candles,
        },
        "news_items": [
            {"headline": h, "source": "mock", "published_at": "", "url": ""}
            for h in (news_headlines or [])
        ],
        "onchain_summary": {},
        "social_summary":  {},
        "data_gaps":       [],
    }
    return state


# --- Sentiment ---

async def test_sentiment_bullish_on_positive_news():
    settings = Settings(LLM_ENABLED=False)
    node  = (lambda s: __import__(
        "agents.analyzers.sentiment_analyzer", fromlist=["make_sentiment_analyzer"]
    ).make_sentiment_analyzer(s))(settings)
    state = _state_with_context(news_headlines=["BTC surges rally gain strong buy"])
    result = await node(state)
    sa = result["sentiment_analysis"]
    assert sa["sentiment_label"] in ("bullish", "neutral")
    assert -1.0 <= sa["sentiment_score"] <= 1.0
    assert isinstance(sa["sentiment_drivers"], list)


async def test_sentiment_neutral_on_empty_news():
    from agents.analyzers.sentiment_analyzer import make_sentiment_analyzer
    node  = make_sentiment_analyzer(Settings(LLM_ENABLED=False))
    state = _state_with_context(news_headlines=[])
    result = await node(state)
    assert result["sentiment_analysis"]["sentiment_label"] == "neutral"


# --- Market structure ---

async def test_market_structure_returns_expected_fields():
    from agents.analyzers.market_structure_analyzer import analyze_market_structure
    state = _state_with_context()
    result = await analyze_market_structure(state)
    ms = result["market_structure_analysis"]

    assert ms["bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= ms["rsi"] <= 100.0
    assert ms["ma_trend"] in ("uptrend", "downtrend", "sideways")
    assert 0.0 <= ms["confidence_score"] <= 1.0
    assert isinstance(ms["explanation"], str)
    assert isinstance(ms["swing_highs"], list)
    assert isinstance(ms["swing_lows"], list)
    assert isinstance(ms["bos_choch"], list)
    assert ms["ml_probability_1r"] is None


async def test_market_structure_insufficient_data_returns_neutral():
    from agents.analyzers.market_structure_analyzer import analyze_market_structure
    state = _state_with_context(ohlcv=[])
    result = await analyze_market_structure(state)
    ms = result["market_structure_analysis"]
    assert ms["bias"] == "neutral"
    assert ms["confidence_score"] == 0.0
    assert ms["swing_highs"] == []
    assert ms["bos_choch"] == []


async def test_market_structure_rsi_in_valid_range():
    from agents.analyzers.market_structure_analyzer import analyze_market_structure
    state = _state_with_context(ohlcv=make_ohlcv(50))
    result = await analyze_market_structure(state)
    rsi = result["market_structure_analysis"]["rsi"]
    assert 0.0 <= rsi <= 100.0


# --- Risk ---

async def test_risk_low_on_stable_market():
    from agents.analyzers.risk_analyzer import make_risk_analyzer
    node  = make_risk_analyzer(Settings(LLM_ENABLED=False))
    state = _state_with_context(price_change=0.5)
    result = await node(state)
    ra = result["risk_analysis"]
    assert ra["risk_level"] in ("low", "medium", "high")
    assert isinstance(ra["risk_factors"], list)
    assert len(ra["risk_factors"]) >= 1


async def test_risk_high_on_volatile_market():
    from agents.analyzers.risk_analyzer import make_risk_analyzer
    node  = make_risk_analyzer(Settings(LLM_ENABLED=False))
    state = _state_with_context(price_change=15.0)
    result = await node(state)
    assert result["risk_analysis"]["risk_level"] in ("medium", "high")
