import pytest
import httpx
import respx
from data_sources.binance.binance_price import BinancePriceAdapter
from data_sources.base import DataSourceAdapter, FallbackAdapter
from data_sources.mock.mock_price import MockPriceAdapter

_TICKER_BASE = "https://api.binance.com/api/v3/ticker/24hr"
_KLINES_BASE  = "https://api.binance.com/api/v3/klines"


def _ticker_payload() -> dict:
    return {
        "symbol":             "BTCUSDT",
        "lastPrice":          "67000.00",
        "priceChangePercent": "2.50",
        "quoteVolume":        "1500000000.00",
        "highPrice":          "68000.00",
        "lowPrice":           "65000.00",
    }


def _klines_payload(n: int = 60) -> list:
    return [
        [
            1_000_000 + i * 3_600_000,   # open_time
            "67000.00",                  # open
            "67500.00",                  # high
            "66500.00",                  # low
            "67200.00",                  # close
            "100.5",                     # volume
            1_003_600_000 + i * 3_600_000,
            "6_720_000",
            1000, "50", "3_360_000", "0",
        ]
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------

async def test_binance_adapter_success():
    with respx.mock:
        respx.get(_TICKER_BASE).mock(return_value=httpx.Response(200, json=_ticker_payload()))
        respx.get(_KLINES_BASE).mock(return_value=httpx.Response(200, json=_klines_payload()))
        result = await BinancePriceAdapter().fetch("BTCUSDT")

    assert result["symbol"] == "BTCUSDT"
    assert result["source"] == "binance"
    assert result["price_usd"] == pytest.approx(67_000.0)
    assert result["change_24h_pct"] == pytest.approx(2.5)
    assert result["high_24h"] == pytest.approx(68_000.0)
    assert len(result["ohlcv_24h"]) == 60


# ---------------------------------------------------------------------------
# 2. OHLCV shape matches market_structure_analyzer expectations
# ---------------------------------------------------------------------------

async def test_binance_adapter_ohlcv_shape():
    with respx.mock:
        respx.get(_TICKER_BASE).mock(return_value=httpx.Response(200, json=_ticker_payload()))
        respx.get(_KLINES_BASE).mock(return_value=httpx.Response(200, json=_klines_payload(30)))
        result = await BinancePriceAdapter().fetch("BTCUSDT")

    candle = result["ohlcv_24h"][0]
    assert set(candle.keys()) == {"open", "high", "low", "close", "volume"}
    assert all(isinstance(v, float) for v in candle.values())
    assert candle["high"] >= candle["low"]


# ---------------------------------------------------------------------------
# 3. HTTP error propagates (FallbackAdapter will catch it)
# ---------------------------------------------------------------------------

async def test_binance_adapter_http_error_raises():
    with respx.mock:
        respx.get(_TICKER_BASE).mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            await BinancePriceAdapter().fetch("BTCUSDT")


# ---------------------------------------------------------------------------
# 4. FallbackAdapter uses mock when Binance raises
# ---------------------------------------------------------------------------

async def test_fallback_uses_mock_when_binance_fails():
    class _FailingAdapter(DataSourceAdapter):
        source_name = "binance"
        async def fetch(self, symbol: str):
            raise RuntimeError("network unreachable")

    adapter = FallbackAdapter([_FailingAdapter(), MockPriceAdapter()])
    result  = await adapter.fetch("BTCUSDT")

    assert result is not None
    assert result["source"] == "mock"
    assert result["price_usd"] > 0
    assert isinstance(result["ohlcv_24h"], list)
