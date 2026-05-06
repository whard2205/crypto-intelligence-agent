from __future__ import annotations
from data_sources.base import DataSourceAdapter

_FUNDING: dict[str, dict] = {
    "BTCUSDT": {"symbol": "BTCUSDT", "funding_rate":  0.00080, "funding_time": "", "source": "mock"},
    "ETHUSDT": {"symbol": "ETHUSDT", "funding_rate": -0.00060, "funding_time": "", "source": "mock"},
}
_DEFAULT = {"funding_rate": 0.00010, "funding_time": "", "source": "mock"}


class MockFundingRateAdapter(DataSourceAdapter):
    source_name = "mock_funding_rate"

    async def fetch(self, symbol: str) -> dict:
        base = _FUNDING.get(symbol, {**_DEFAULT, "symbol": symbol})
        return {**base, "symbol": symbol}
