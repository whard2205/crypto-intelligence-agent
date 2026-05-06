import math
import sys
from unittest.mock import patch

import pytest

from tests.conftest import make_ohlcv


def _make_uptrend_ohlcv(n: int = 60) -> list[dict]:
    """60 candles: downtrend first half, strong uptrend second half.
    Gives HMM clearly distinct state means so the last candle lands in bull_trending."""
    candles = []
    half = n // 2
    for i in range(n):
        if i < half:
            close = 100.0 * (0.990 ** i)           # -1% per candle
        else:
            close = 100.0 * (0.990 ** half) * (1.020 ** (i - half))  # +2% per candle
        open_ = close * 0.999
        candles.append({
            "open": round(open_, 4), "high": round(close * 1.003, 4),
            "low": round(open_ * 0.997, 4), "close": round(close, 4),
            "volume": 10000,
        })
    return candles


def test_valid_input_returns_regime_dict():
    from graph.hmm_regime import detect_hmm_regime
    result = detect_hmm_regime(make_ohlcv(60))
    assert result is not None
    assert result["regime"] in {"bull_trending", "ranging", "bear_trending"}
    assert result["n_states"] == 3
    assert result["source"] == "hmm"


def test_short_input_returns_none():
    from graph.hmm_regime import detect_hmm_regime
    result = detect_hmm_regime(make_ohlcv(29))
    assert result is None


def test_import_error_returns_none():
    from graph.hmm_regime import detect_hmm_regime
    blocked = {"hmmlearn": None, "hmmlearn.hmm": None}
    with patch.dict(sys.modules, blocked):
        result = detect_hmm_regime(make_ohlcv(60))
    assert result is None


def test_uptrend_data_regime_is_bull_trending():
    from graph.hmm_regime import detect_hmm_regime
    result = detect_hmm_regime(_make_uptrend_ohlcv(60))
    assert result is not None
    assert result["regime"] == "bull_trending"


def test_does_not_mutate_input():
    from graph.hmm_regime import detect_hmm_regime
    ohlcv = make_ohlcv(60)
    original = [dict(c) for c in ohlcv]
    detect_hmm_regime(ohlcv)
    assert ohlcv == original


def test_deterministic_with_random_state():
    from graph.hmm_regime import detect_hmm_regime
    ohlcv = make_ohlcv(60)
    result1 = detect_hmm_regime(ohlcv)
    result2 = detect_hmm_regime(ohlcv)
    assert result1 == result2
