from __future__ import annotations
from data_sources.base import DataSourceAdapter

_ONCHAIN: dict[str, dict] = {
    "BTCUSDT": {
        "network":             "bitcoin",
        "active_addresses_24h": 1_050_000,
        "transactions_24h":    320_000,
        "hash_rate":           620_000_000_000_000_000,
        "mempool_size":        12_500,
        "source":              "mock",
    },
    "ETHUSDT": {
        "network":          "ethereum",
        "active_addresses_24h": 740_000,
        "transactions_24h": 1_100_000,
        "gas_price_gwei":   18.5,
        "eth_supply":       120_200_000,
        "source":           "mock",
    },
}
_DEFAULT_ONCHAIN = {
    "network": "unknown",
    "active_addresses_24h": 0,
    "transactions_24h": 0,
    "source": "mock",
}


class MockOnChainAdapter(DataSourceAdapter):
    source_name = "mock_onchain"

    async def fetch(self, symbol: str) -> dict:
        return _ONCHAIN.get(symbol, _DEFAULT_ONCHAIN)
