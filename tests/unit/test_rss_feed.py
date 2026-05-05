import pytest
import httpx
import respx
from data_sources.news.rss_feed import RSSFeedAdapter

_FEED_URL = "https://example.com/rss"

_RSS_BTC = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CryptoNews</title>
    <item>
      <title>Bitcoin breaks $65K on ETF inflows</title>
      <link>https://example.com/btc-65k</link>
      <description>Bitcoin surged past the $65,000 mark as ETF inflows accelerated.</description>
      <pubDate>Mon, 04 May 2026 08:00:00 +0000</pubDate>
    </item>
    <item>
      <title>BTC accumulation at all-time high</title>
      <link>https://example.com/btc-atl</link>
      <description>Bitcoin whale accumulation reaches record levels.</description>
      <pubDate>Mon, 04 May 2026 06:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Ethereum gas fees drop sharply</title>
      <link>https://example.com/eth-gas</link>
      <description>Ethereum network activity shows reduced gas costs.</description>
      <pubDate>Mon, 04 May 2026 05:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

_RSS_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CryptoNews</title>
  </channel>
</rss>"""


# ---------------------------------------------------------------------------
# 1. Returns relevant items for known symbol
# ---------------------------------------------------------------------------

async def test_rss_feed_returns_relevant_items():
    adapter = RSSFeedAdapter(feeds=[_FEED_URL])
    with respx.mock:
        respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_RSS_BTC))
        result = await adapter.fetch("BTCUSDT")

    assert result is not None
    assert len(result) == 2  # Only BTC-relevant items
    titles = [item["title"] for item in result]
    assert any("Bitcoin" in t or "BTC" in t for t in titles)


# ---------------------------------------------------------------------------
# 2. Item schema is correct
# ---------------------------------------------------------------------------

async def test_rss_feed_item_schema():
    adapter = RSSFeedAdapter(feeds=[_FEED_URL])
    with respx.mock:
        respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_RSS_BTC))
        result = await adapter.fetch("BTCUSDT")

    item = result[0]
    assert "title" in item
    assert "source" in item
    assert "published_at" in item
    assert "url" in item
    assert "summary" in item
    assert isinstance(item["title"], str)
    assert isinstance(item["url"], str)


# ---------------------------------------------------------------------------
# 3. Returns None when all feeds fail
# ---------------------------------------------------------------------------

async def test_rss_feed_returns_none_when_all_fail():
    adapter = RSSFeedAdapter(feeds=[_FEED_URL])
    with respx.mock:
        respx.get(_FEED_URL).mock(return_value=httpx.Response(503))
        result = await adapter.fetch("BTCUSDT")

    assert result is None


# ---------------------------------------------------------------------------
# 4. Returns None when feed succeeds but no relevant items
# ---------------------------------------------------------------------------

async def test_rss_feed_returns_none_when_no_relevant_items():
    adapter = RSSFeedAdapter(feeds=[_FEED_URL])
    with respx.mock:
        respx.get(_FEED_URL).mock(return_value=httpx.Response(200, text=_RSS_EMPTY))
        result = await adapter.fetch("BTCUSDT")

    # Feed succeeded but 0 relevant items → None
    assert result is None


# ---------------------------------------------------------------------------
# 5. Falls back to next feed on error
# ---------------------------------------------------------------------------

async def test_rss_feed_falls_back_to_second_feed():
    feed2 = "https://example.com/rss2"
    adapter = RSSFeedAdapter(feeds=[_FEED_URL, feed2])
    with respx.mock:
        respx.get(_FEED_URL).mock(return_value=httpx.Response(503))
        respx.get(feed2).mock(return_value=httpx.Response(200, text=_RSS_BTC))
        result = await adapter.fetch("BTCUSDT")

    assert result is not None
    assert len(result) >= 1
