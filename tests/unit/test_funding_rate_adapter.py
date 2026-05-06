import pytest
import httpx
import respx
from data_sources.mock.mock_funding_rate import MockFundingRateAdapter
from data_sources.binance.binance_funding_rate import BinanceFundingRateAdapter
from data_sources.base import DataSourceAdapter, FallbackAdapter


async def test_mock_adapter_btcusdt():
    result = await MockFundingRateAdapter().fetch("BTCUSDT")
    assert result is not None
    assert result["funding_rate"] == pytest.approx(0.00080)
    assert result["source"] == "mock"
    assert "funding_time" in result
    assert result["symbol"] == "BTCUSDT"


async def test_mock_adapter_ethusdt():
    result = await MockFundingRateAdapter().fetch("ETHUSDT")
    assert result is not None
    assert result["funding_rate"] == pytest.approx(-0.00060)
    assert result["source"] == "mock"


async def test_mock_adapter_unknown_symbol_returns_neutral_default():
    result = await MockFundingRateAdapter().fetch("SOLUSDT")
    assert result is not None
    assert result["funding_rate"] == pytest.approx(0.00010)
    assert result["source"] == "mock"


_FAPI_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def _funding_payload(rate: str = "0.00080000", ts: int = 1_746_518_400_000) -> list:
    return [{"symbol": "BTCUSDT", "fundingTime": ts, "fundingRate": rate, "markPrice": "95000.00"}]


async def test_binance_adapter_success():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(200, json=_funding_payload()))
        result = await BinanceFundingRateAdapter().fetch("BTCUSDT")

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["funding_rate"] == pytest.approx(0.00080)
    assert result["source"] == "binance"
    assert result["funding_time"].endswith("Z")   # ISO UTC string


async def test_binance_adapter_empty_list_returns_none():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(200, json=[]))
        result = await BinanceFundingRateAdapter().fetch("BTCUSDT")
    assert result is None


async def test_binance_adapter_404_returns_none():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(404))
        result = await BinanceFundingRateAdapter().fetch("BTCUSDT")
    assert result is None


async def test_binance_adapter_503_raises():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            await BinanceFundingRateAdapter().fetch("BTCUSDT")


async def test_fallback_uses_mock_when_binance_fails():
    class _Failing(DataSourceAdapter):
        source_name = "binance_funding_rate"
        async def fetch(self, symbol: str):
            raise RuntimeError("network unreachable")

    adapter = FallbackAdapter([_Failing(), MockFundingRateAdapter()])
    result  = await adapter.fetch("BTCUSDT")
    assert result is not None
    assert result["source"] == "mock"
