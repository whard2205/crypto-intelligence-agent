from __future__ import annotations
from data_sources.base import DataSourceAdapter

_SOCIAL: dict[str, dict] = {
    "BTCUSDT": {
        "symbol":       "BTCUSDT",
        "post_count":   42,
        "top_posts": [
            {"title": "BTC breaking out — target $70K", "score": 2840, "comments": 312},
            {"title": "Bitcoin accumulation phase seems over",  "score": 1950, "comments": 208},
            {"title": "Institutional buy pressure is real",      "score": 1420, "comments": 175},
        ],
        "source": "mock",
    },
    "ETHUSDT": {
        "symbol":       "ETHUSDT",
        "post_count":   28,
        "top_posts": [
            {"title": "ETH merge upgrade impact still undervalued", "score": 1640, "comments": 194},
            {"title": "Layer-2 fee reduction attracts new users",   "score": 1120, "comments": 143},
        ],
        "source": "mock",
    },
}
_DEFAULT_SOCIAL = {
    "symbol":     "UNKNOWN",
    "post_count": 5,
    "top_posts":  [],
    "source":     "mock",
}


class MockSocialAdapter(DataSourceAdapter):
    source_name = "mock_social"

    async def fetch(self, symbol: str) -> dict:
        return _SOCIAL.get(symbol, {**_DEFAULT_SOCIAL, "symbol": symbol})
