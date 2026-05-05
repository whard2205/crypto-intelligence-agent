from __future__ import annotations
from data_sources.base import DataSourceAdapter

_HEADLINES: dict[str, list[dict]] = {
    "BTCUSDT": [
        {"title": "Bitcoin surges past $65K as institutional demand accelerates",
         "source": "MockNews", "published_at": "2026-05-03T08:00:00Z",
         "url": "https://example.com/btc-surge"},
        {"title": "BTC accumulation by ETF funds reaches all-time high",
         "source": "MockNews", "published_at": "2026-05-03T06:30:00Z",
         "url": "https://example.com/btc-etf"},
        {"title": "Bitcoin rally gains momentum amid macro uncertainty",
         "source": "MockNews", "published_at": "2026-05-03T04:00:00Z",
         "url": "https://example.com/btc-rally"},
    ],
    "ETHUSDT": [
        {"title": "Ethereum layer-2 activity hits record high",
         "source": "MockNews", "published_at": "2026-05-03T09:00:00Z",
         "url": "https://example.com/eth-l2"},
        {"title": "ETH staking rewards rise as validators increase",
         "source": "MockNews", "published_at": "2026-05-03T07:00:00Z",
         "url": "https://example.com/eth-stake"},
    ],
}
_DEFAULT_HEADLINES = [
    {"title": "Crypto market shows bullish momentum",
     "source": "MockNews", "published_at": "2026-05-03T08:00:00Z",
     "url": "https://example.com/crypto"},
    {"title": "Digital assets gain strength on macro tailwinds",
     "source": "MockNews", "published_at": "2026-05-03T06:00:00Z",
     "url": "https://example.com/macro"},
]


class MockNewsAdapter(DataSourceAdapter):
    source_name = "mock_news"

    async def fetch(self, symbol: str) -> list[dict]:
        return _HEADLINES.get(symbol, _DEFAULT_HEADLINES)
