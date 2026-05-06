import pytest
from data_sources.mock.mock_funding_rate import MockFundingRateAdapter


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
