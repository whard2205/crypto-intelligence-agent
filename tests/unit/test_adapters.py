import pytest
from unittest.mock import AsyncMock
from data_sources.base import DataSourceAdapter, FallbackAdapter


class _OKAdapter(DataSourceAdapter):
    source_name = "ok"
    async def fetch(self, symbol): return {"symbol": symbol, "source": "ok"}


class _NoneAdapter(DataSourceAdapter):
    source_name = "none"
    async def fetch(self, symbol): return None


class _ErrorAdapter(DataSourceAdapter):
    source_name = "error"
    async def fetch(self, symbol): raise RuntimeError("boom")


async def test_fallback_returns_first_non_none():
    adapter = FallbackAdapter([_NoneAdapter(), _OKAdapter()])
    result = await adapter.fetch("BTCUSDT")
    assert result is not None
    assert result["source"] == "ok"


async def test_fallback_skips_error_adapter():
    adapter = FallbackAdapter([_ErrorAdapter(), _OKAdapter()])
    result = await adapter.fetch("BTCUSDT")
    assert result["source"] == "ok"


async def test_fallback_returns_none_when_all_fail():
    adapter = FallbackAdapter([_NoneAdapter(), _ErrorAdapter()])
    result = await adapter.fetch("BTCUSDT")
    assert result is None


async def test_fallback_returns_first_result_without_calling_rest():
    second = AsyncMock(spec=DataSourceAdapter, source_name="second")
    second.fetch = AsyncMock(return_value={"source": "second"})
    adapter = FallbackAdapter([_OKAdapter(), second])
    await adapter.fetch("BTCUSDT")
    second.fetch.assert_not_called()


async def test_mock_price_adapter_returns_ohlcv():
    from data_sources.mock.mock_price import MockPriceAdapter
    result = await MockPriceAdapter().fetch("BTCUSDT")
    assert result["symbol"] == "BTCUSDT"
    assert result["price_usd"] > 0
    assert isinstance(result["ohlcv_24h"], list)
    assert len(result["ohlcv_24h"]) >= 10


async def test_mock_news_adapter_returns_headlines():
    from data_sources.mock.mock_news import MockNewsAdapter
    result = await MockNewsAdapter().fetch("BTCUSDT")
    assert isinstance(result, list)
    assert len(result) > 0
    assert "title" in result[0]


async def test_mock_onchain_adapter_returns_dict():
    from data_sources.mock.mock_onchain import MockOnChainAdapter
    result = await MockOnChainAdapter().fetch("BTCUSDT")
    assert isinstance(result, dict)
    assert "network" in result


async def test_mock_social_adapter_returns_dict():
    from data_sources.mock.mock_social import MockSocialAdapter
    result = await MockSocialAdapter().fetch("BTCUSDT")
    assert isinstance(result, dict)
    assert "post_count" in result
