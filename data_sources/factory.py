from __future__ import annotations
from config.settings import Settings
from data_sources.base import DataSourceAdapter, FallbackAdapter
from data_sources.mock.mock_price import MockPriceAdapter
from data_sources.mock.mock_news import MockNewsAdapter
from data_sources.mock.mock_onchain import MockOnChainAdapter
from data_sources.mock.mock_social import MockSocialAdapter


def build_adapters(settings: Settings) -> dict[str, DataSourceAdapter]:
    """Return adapters for build_graph.

    Price routing:
      MOCK_MODE=true              → mock only
      MOCK_MODE=false + dev/test  → Binance → CoinGecko → mock
      MOCK_MODE=false + production → Binance → CoinGecko (no mock fallback)

    News routing:
      MOCK_MODE=true              → mock only
      MOCK_MODE=false + dev/test  → RSS → mock
      MOCK_MODE=false + production → RSS only (no mock fallback)
    """
    if settings.MOCK_MODE:
        price_adapter: DataSourceAdapter = MockPriceAdapter()
        news_adapter:  DataSourceAdapter = MockNewsAdapter()
    else:
        from data_sources.binance.binance_price import BinancePriceAdapter
        from data_sources.coingecko.coingecko_price import CoinGeckoPriceAdapter
        from data_sources.news.rss_feed import RSSFeedAdapter

        if settings.ENV in ("development", "test"):
            price_adapter = FallbackAdapter(
                [BinancePriceAdapter(), CoinGeckoPriceAdapter(), MockPriceAdapter()]
            )
            news_adapter = FallbackAdapter([RSSFeedAdapter(), MockNewsAdapter()])
        else:
            price_adapter = FallbackAdapter(
                [BinancePriceAdapter(), CoinGeckoPriceAdapter()]
            )
            news_adapter = RSSFeedAdapter()

    return {
        "price_adapter":   price_adapter,
        "news_adapter":    news_adapter,
        "onchain_adapter": MockOnChainAdapter(),
        "social_adapter":  MockSocialAdapter(),
    }
