import pytest
from config.settings import Settings
from agents.analyzers.risk_analyzer import make_risk_analyzer
from tests.conftest import make_state


def _make_settings() -> Settings:
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


def _state_with_funding(rate: float) -> dict:
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {"price": 65000.0, "change_24h_pct": 2.0,
                          "volume_24h": 28e9, "high_24h": 66000.0,
                          "low_24h": 64000.0, "ohlcv_24h": []},
        "news_items": [], "onchain_summary": {}, "social_summary": {},
        "data_gaps": [],
        "funding_rate_summary": {"rate": rate, "funding_time": "", "source": "binance"},
    }
    return state


def _state_without_funding() -> dict:
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {"price": 65000.0, "change_24h_pct": 2.0,
                          "volume_24h": 28e9, "high_24h": 66000.0,
                          "low_24h": 64000.0, "ohlcv_24h": []},
        "news_items": [], "onchain_summary": {}, "social_summary": {},
        "data_gaps": [], "funding_rate_summary": None,
    }
    return state


async def test_extreme_positive_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0018))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "longs" in f for f in rf)


async def test_moderate_positive_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0008))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "longs" in f for f in rf)


async def test_extreme_negative_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0020))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "shorts" in f for f in rf)


async def test_moderate_negative_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0006))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "shorts" in f for f in rf)


async def test_neutral_rate_no_funding_signal():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0001))
    rf     = result["risk_analysis"]["risk_factors"]
    assert not any("funding rate" in f.lower() for f in rf)


async def test_missing_funding_summary_no_error():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_without_funding())
    assert "risk_analysis" in result
    rf = result["risk_analysis"]["risk_factors"]
    assert not any("funding rate" in f.lower() for f in rf)


# --- Boundary tests (inclusive thresholds) ---

async def test_boundary_moderate_positive():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0005))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "longs" in f for f in rf)


async def test_boundary_moderate_negative():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0005))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "shorts" in f for f in rf)


async def test_boundary_extreme_positive():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0015))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "longs" in f for f in rf)


async def test_boundary_extreme_negative():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0015))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "shorts" in f for f in rf)
