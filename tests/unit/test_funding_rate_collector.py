import pytest
from data_sources.base import DataSourceAdapter
from agents.collectors.funding_rate_collector import make_funding_rate_collector
from tests.conftest import make_state


class _SuccessAdapter(DataSourceAdapter):
    source_name = "mock"
    async def fetch(self, symbol: str) -> dict:
        return {"symbol": symbol, "funding_rate": 0.00080, "funding_time": "", "source": "mock"}


class _NoneAdapter(DataSourceAdapter):
    source_name = "mock"
    async def fetch(self, symbol: str):
        return None


class _RaisingAdapter(DataSourceAdapter):
    source_name = "mock"
    async def fetch(self, symbol: str):
        raise RuntimeError("network error")


async def test_collector_success():
    node   = make_funding_rate_collector(_SuccessAdapter())
    result = await node(make_state())
    assert "funding_rate_data" in result
    assert result["funding_rate_data"]["funding_rate"] == pytest.approx(0.00080)


async def test_collector_adapter_returns_none_adds_data_gap():
    node   = make_funding_rate_collector(_NoneAdapter())
    result = await node(make_state())
    assert "funding_rate_data" not in result
    assert "funding_unavailable" in result.get("data_gaps", [])


async def test_collector_adapter_raises_adds_data_gap_no_crash():
    node   = make_funding_rate_collector(_RaisingAdapter())
    result = await node(make_state())
    assert "funding_rate_data" not in result
    assert "funding_unavailable" in result.get("data_gaps", [])
