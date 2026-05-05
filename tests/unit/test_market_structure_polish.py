"""Tests for SMC polish fixes:
  Fix 1 — _deduplicate_bos: consecutive same-direction BOS deduplication
  Fix 2 — volume=0 data quality flag in explanation
"""
import pytest
from agents.analyzers.market_structure_analyzer import (
    _deduplicate_bos,
    analyze_market_structure,
)
from tests.conftest import make_state, make_ohlcv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bos(direction: str, break_level: float, candle_idx: int, type_: str = "BOS") -> dict:
    return {"type": type_, "direction": direction,
            "break_level": break_level, "candle_idx": candle_idx}


def _zero_volume_ohlcv(n: int = 40) -> list[dict]:
    """Same shape as make_ohlcv but all volumes = 0."""
    candles = make_ohlcv(n)
    return [{**c, "volume": 0} for c in candles]


def _state_with_ohlcv(ohlcv: list[dict]) -> dict:
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {
            "price": 65000.0, "change_24h_pct": 2.0,
            "volume_24h": 28e9, "high_24h": 66000.0, "low_24h": 64000.0,
            "ohlcv_24h": ohlcv,
        },
        "news_items": [], "onchain_summary": {}, "social_summary": {}, "data_gaps": [],
    }
    return state


# ---------------------------------------------------------------------------
# Fix 1 — _deduplicate_bos unit tests
# ---------------------------------------------------------------------------

def test_dedup_consecutive_bullish_keeps_higher_level():
    """Two bullish BOS 1 candle apart, levels 0.08% apart → merged to higher."""
    events = [
        _make_bos("bullish", 81216.0, 45),
        _make_bos("bullish", 81278.0, 46),   # 0.077% diff → below 0.15% threshold
    ]
    result = _deduplicate_bos(events)
    assert len(result) == 1
    assert result[0]["break_level"] == 81278.0   # higher level kept


def test_dedup_consecutive_bearish_keeps_lower_level():
    """Two bearish BOS 1 candle apart, close levels → merged to lower."""
    events = [
        _make_bos("bearish", 79800.0, 10),
        _make_bos("bearish", 79750.0, 11),   # 0.063% diff → below threshold
    ]
    result = _deduplicate_bos(events)
    assert len(result) == 1
    assert result[0]["break_level"] == 79750.0   # lower level kept for bearish


def test_dedup_opposite_directions_not_merged():
    """Bearish CHOCH then bullish CHOCH — must NOT be merged even if close candles."""
    events = [
        _make_bos("bearish",  79750.0, 2,  type_="CHOCH"),
        _make_bos("bullish",  81136.0, 44, type_="CHOCH"),
    ]
    result = _deduplicate_bos(events)
    assert len(result) == 2


def test_dedup_same_direction_far_apart_candles_not_merged():
    """Same direction but 10 candles apart → NOT merged."""
    events = [
        _make_bos("bullish", 81000.0, 10),
        _make_bos("bullish", 81050.0, 20),   # 10 candles apart > threshold of 2
    ]
    result = _deduplicate_bos(events)
    assert len(result) == 2


def test_dedup_same_direction_large_level_diff_not_merged():
    """Same direction, adjacent candles, but 0.5% level difference → NOT merged."""
    events = [
        _make_bos("bullish", 80000.0, 10),
        _make_bos("bullish", 80400.0, 11),   # 0.5% diff > 0.15% threshold
    ]
    result = _deduplicate_bos(events)
    assert len(result) == 2


def test_dedup_chain_of_three_collapses_to_one():
    """Three consecutive bullish BOS all within threshold → all collapsed to one."""
    events = [
        _make_bos("bullish", 81200.0, 44),
        _make_bos("bullish", 81216.0, 45),
        _make_bos("bullish", 81278.0, 46),
    ]
    result = _deduplicate_bos(events)
    assert len(result) == 1
    assert result[0]["break_level"] == 81278.0


def test_dedup_preserves_unrelated_events():
    """CHOCH bearish → CHOCH bullish (far apart) → BOS bullish (consecutive) → 2 results."""
    events = [
        _make_bos("bearish",  79750.0, 2,  type_="CHOCH"),
        _make_bos("bullish",  81136.0, 44, type_="CHOCH"),
        _make_bos("bullish",  81278.0, 46, type_="BOS"),   # 2 candles from idx 44
    ]
    # idx 44 and 46 are 2 candles apart, level diff: (81278-81136)/81278 = 0.17% > threshold
    result = _deduplicate_bos(events)
    # bearish and bullish: no merge; bullish pair: 0.17% > 0.15% so no merge
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Fix 2 — volume=0 data quality flag (integration tests)
# ---------------------------------------------------------------------------

async def test_zero_volume_adds_unavailable_note():
    """All-zero volumes → explanation contains 'volume data unavailable'."""
    state = _state_with_ohlcv(_zero_volume_ohlcv(40))
    result = await analyze_market_structure(state)
    ms = result["market_structure_analysis"]
    assert "volume data unavailable" in ms["explanation"]
    assert ms["volume_confirmed"] is False


async def test_zero_volume_does_not_set_volume_confirmed():
    """Zero-volume candles must not set volume_confirmed=True."""
    state = _state_with_ohlcv(_zero_volume_ohlcv(40))
    result = await analyze_market_structure(state)
    assert result["market_structure_analysis"]["volume_confirmed"] is False


async def test_normal_volume_no_unavailable_note():
    """Normal non-zero volumes → explanation does NOT mention 'volume data unavailable'."""
    state = _state_with_ohlcv(make_ohlcv(40))
    result = await analyze_market_structure(state)
    ms = result["market_structure_analysis"]
    assert "volume data unavailable" not in ms["explanation"]
