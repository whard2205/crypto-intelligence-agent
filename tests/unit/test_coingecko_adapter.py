import pytest
import httpx
import respx
from data_sources.coingecko.coingecko_price import CoinGeckoPriceAdapter

_SIMPLE_BASE = "https://api.coingecko.com/api/v3/simple/price"
_OHLC_BASE   = "https://api.coingecko.com/api/v3/coins/bitcoin/ohlc"


def _price_payload() -> dict:
    return {
        "bitcoin": {
            "usd": 65000.0,
            "usd_24h_change": 2.5,
            "usd_24h_vol": 28_000_000_000.0,
            "usd_market_cap": 1_280_000_000_000.0,
        }
    }


def _ohlc_payload(n: int = 24) -> list:
    # Each entry: [timestamp_ms, open, high, low, close]
    return [
        [1_000_000 + i * 3_600_000, 64800.0 + i * 10, 65200.0 + i * 10,
         64500.0 + i * 10, 65000.0 + i * 10]
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------

async def test_coingecko_adapter_success():
    with respx.mock:
        respx.get(_SIMPLE_BASE).mock(return_value=httpx.Response(200, json=_price_payload()))
        respx.get(_OHLC_BASE).mock(return_value=httpx.Response(200, json=_ohlc_payload()))
        result = await CoinGeckoPriceAdapter().fetch("BTCUSDT")

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["source"] == "coingecko"
    assert result["price_usd"] == pytest.approx(65_000.0)
    assert result["change_24h_pct"] == pytest.approx(2.5)
    assert result["volume_24h_usd"] == pytest.approx(28_000_000_000.0)
    assert len(result["ohlcv_24h"]) == 24


# ---------------------------------------------------------------------------
# 2. OHLCV shape
# ---------------------------------------------------------------------------

async def test_coingecko_adapter_ohlcv_shape():
    with respx.mock:
        respx.get(_SIMPLE_BASE).mock(return_value=httpx.Response(200, json=_price_payload()))
        respx.get(_OHLC_BASE).mock(return_value=httpx.Response(200, json=_ohlc_payload(10)))
        result = await CoinGeckoPriceAdapter().fetch("BTCUSDT")

    candle = result["ohlcv_24h"][0]
    assert set(candle.keys()) == {"open", "high", "low", "close", "volume"}
    assert candle["volume"] == 0.0
    assert candle["high"] >= candle["low"]


# ---------------------------------------------------------------------------
# 3. Unknown symbol returns None
# ---------------------------------------------------------------------------

async def test_coingecko_adapter_unknown_symbol_returns_none():
    result = await CoinGeckoPriceAdapter().fetch("UNKNOWNUSDT")
    assert result is None


# ---------------------------------------------------------------------------
# 4. HTTP error propagates
# ---------------------------------------------------------------------------

async def test_coingecko_adapter_http_error_raises():
    with respx.mock:
        respx.get(_SIMPLE_BASE).mock(return_value=httpx.Response(429))
        with pytest.raises(httpx.HTTPStatusError):
            await CoinGeckoPriceAdapter().fetch("BTCUSDT")


# ---------------------------------------------------------------------------
# 5. High/low derived from OHLC candles
# ---------------------------------------------------------------------------

async def test_coingecko_adapter_high_low_from_ohlc():
    candles = _ohlc_payload(5)
    with respx.mock:
        respx.get(_SIMPLE_BASE).mock(return_value=httpx.Response(200, json=_price_payload()))
        respx.get(_OHLC_BASE).mock(return_value=httpx.Response(200, json=candles))
        result = await CoinGeckoPriceAdapter().fetch("BTCUSDT")

    expected_high = max(c[2] for c in candles)
    expected_low  = min(c[3] for c in candles)
    assert result["high_24h"] == pytest.approx(expected_high)
    assert result["low_24h"]  == pytest.approx(expected_low)
