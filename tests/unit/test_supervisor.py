import pytest
from config.settings import Settings
from agents.supervisor import make_supervisor
from tests.conftest import make_state


def _state_with_full_analysis(**analysis_overrides):

    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {
            "price": 65000.0, "change_24h_pct": 2.3,
            "volume_24h": 28e9, "high_24h": 66000.0, "low_24h": 64000.0,
            "ohlcv_24h": [],
        },
        "news_items": [], "onchain_summary": {},
        "social_summary": {}, "data_gaps": [],
    }
    default_ms = {
        "bias": "bullish", "rsi": 58.0, "ma_trend": "uptrend",
        "confidence_score": 0.65, "explanation": "BOS bullish",
        "swing_highs": [65100.0], "swing_lows": [63900.0],
        "liquidity_sweeps": [], "order_blocks": [],
        "bos_choch": [{"type": "BOS", "direction": "bullish",
                       "break_level": 65100.0, "candle_idx": 25}],
        "volume_confirmed": True, "invalidation_level": 63900.0,
        "macd_histogram_slope": 0.002, "momentum_pct": 1.2,
        "ml_probability_1r": None, "ml_probability_2r": None,
    }
    state["analysis"] = {
        "sentiment_score": 0.3, "sentiment_label": "bullish",
        "sentiment_drivers": ["BTC surges"],
        "market_structure": default_ms,
        "risk_level": "low", "risk_factors": [],
        **analysis_overrides,
    }
    return state


async def test_supervisor_returns_intelligence_report():
    node  = make_supervisor(Settings(LLM_ENABLED=False))
    state = _state_with_full_analysis()
    result = await node(state)
    report = result["report"]

    assert not report.get("error")
    assert report["symbol"] == "BTCUSDT"
    assert report["market_bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= report["confidence_score"] <= 1.0
    assert isinstance(report["key_signals"], list)
    assert len(report["key_signals"]) >= 1
    assert isinstance(report["narrative"], str)
    assert report["llm_used"] is False
    assert report["analysis_engine"] == "rule-based"
    assert "price_source" in report
    assert "news_source" in report


async def test_supervisor_bias_reflects_market_structure():
    node  = make_supervisor(Settings(LLM_ENABLED=False))
    state = _state_with_full_analysis()
    result = await node(state)
    # Market structure is bullish with 2× weight + bullish sentiment: should be bullish
    assert result["report"]["market_bias"] == "bullish"


async def test_supervisor_lowers_confidence_with_gaps():
    node = make_supervisor(Settings(LLM_ENABLED=False))

    state_no_gaps   = _state_with_full_analysis()
    state_with_gaps = _state_with_full_analysis()
    state_with_gaps["context"]["data_gaps"] = ["social_unavailable", "onchain_unavailable"]

    conf_clean  = (await node(state_no_gaps))["report"]["confidence_score"]
    conf_gapped = (await node(state_with_gaps))["report"]["confidence_score"]
    assert conf_clean >= conf_gapped


async def test_supervisor_handles_empty_analysis():
    node  = make_supervisor(Settings(LLM_ENABLED=False))
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT", "price_summary": {"change_24h_pct": 0},
        "news_items": [], "onchain_summary": {}, "social_summary": {}, "data_gaps": [],
    }
    state["analysis"] = {
        "sentiment_score": None, "sentiment_label": None,
        "sentiment_drivers": None, "market_structure": None,
        "risk_level": None, "risk_factors": None,
    }
    result = await node(state)
    assert "market_bias" in result["report"]


# ---------------------------------------------------------------------------
# Helpers for RSI-specific tests
# ---------------------------------------------------------------------------

def _state_with_rsi(rsi: float, bias: str = "bullish", risk_level: str = "low") -> dict:
    state = _state_with_full_analysis()
    ms = {**state["analysis"]["market_structure"], "rsi": rsi, "bias": bias}
    state["analysis"] = {**state["analysis"], "market_structure": ms, "risk_level": risk_level}
    return state


# ---------------------------------------------------------------------------
# Risk consistency tests
# ---------------------------------------------------------------------------

async def test_rsi_overbought_adds_pullback_warning():
    """RSI >= 70 must produce the overbought pullback warning."""
    node   = make_supervisor(Settings(LLM_ENABLED=False))
    state  = _state_with_rsi(rsi=73.0)
    report = (await node(state))["report"]
    assert "RSI overbought — pullback risk elevated" in report["risk_warnings"]


async def test_rsi_75_bullish_not_low_risk():
    """RSI >= 75 with bullish bias must not produce risk_level=low in narrative."""
    node   = make_supervisor(Settings(LLM_ENABLED=False))
    state  = _state_with_rsi(rsi=76.0, bias="bullish", risk_level="low")
    report = (await node(state))["report"]
    assert "Risk: low" not in report["narrative"]
    assert "Risk: medium" in report["narrative"] or "Risk: high" in report["narrative"]


async def test_narrative_no_low_risk_when_overbought():
    """RSI in 70-74 range still triggers the consistency cap (rule B)."""
    node   = make_supervisor(Settings(LLM_ENABLED=False))
    state  = _state_with_rsi(rsi=72.0, bias="bullish", risk_level="low")
    report = (await node(state))["report"]
    # Warning exists → risk_level upgraded → narrative must not say "Risk: low"
    assert "RSI overbought — pullback risk elevated" in report["risk_warnings"]
    assert "Risk: low" not in report["narrative"]


async def test_rsi_70_narrative_mentions_pullback():
    """Narrative must contain pullback mention whenever RSI >= 70."""
    node   = make_supervisor(Settings(LLM_ENABLED=False))
    state  = _state_with_rsi(rsi=71.0)
    report = (await node(state))["report"]
    assert "pullback" in report["narrative"].lower()


# ---------------------------------------------------------------------------
# Market regime context injection
# ---------------------------------------------------------------------------

def _ms_with_regime(regime: str | None) -> dict:
    base = {
        "bias": "bullish", "rsi": 58.0, "ma_trend": "uptrend",
        "confidence_score": 0.65, "explanation": "BOS bullish",
        "swing_highs": [65100.0], "swing_lows": [63900.0],
        "liquidity_sweeps": [], "order_blocks": [],
        "bos_choch": [{"type": "BOS", "direction": "bullish",
                       "break_level": 65100.0, "candle_idx": 25}],
        "volume_confirmed": True, "invalidation_level": 63900.0,
        "macd_histogram_slope": 0.002, "momentum_pct": 1.2,
        "ml_probability_1r": None, "ml_probability_2r": None,
        "market_regime": None,
    }
    if regime is not None:
        base["market_regime"] = {"regime": regime, "n_states": 3, "source": "hmm"}
    return base


async def test_supervisor_aligned_regime_adds_signal_and_boosts_confidence():
    node = make_supervisor(Settings(LLM_ENABLED=False))

    state_no      = _state_with_full_analysis()
    state_aligned = _state_with_full_analysis(market_structure=_ms_with_regime("bull_trending"))

    result_no      = await node(state_no)
    result_aligned = await node(state_aligned)

    signals = result_aligned["report"]["key_signals"]
    assert any("Market Regime Context: bull_trending" in s for s in signals)
    assert result_aligned["report"]["confidence_score"] >= result_no["report"]["confidence_score"]


async def test_supervisor_misaligned_regime_adds_signal_no_boost():
    node = make_supervisor(Settings(LLM_ENABLED=False))

    state_no       = _state_with_full_analysis()
    state_mismatch = _state_with_full_analysis(market_structure=_ms_with_regime("ranging"))

    result_no       = await node(state_no)
    result_mismatch = await node(state_mismatch)

    signals = result_mismatch["report"]["key_signals"]
    assert any("Market Regime Context: ranging" in s for s in signals)
    assert result_mismatch["report"]["confidence_score"] == result_no["report"]["confidence_score"]


async def test_supervisor_none_regime_no_injection():
    node = make_supervisor(Settings(LLM_ENABLED=False))
    state = _state_with_full_analysis()
    result = await node(state)
    assert not any("Market Regime Context" in s for s in result["report"]["key_signals"])
