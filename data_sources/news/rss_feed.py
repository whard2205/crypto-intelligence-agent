from __future__ import annotations
from typing import Optional
import logging
import feedparser
import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0

# Feeds that publish broad crypto news — symbol-agnostic; caller filters by relevance.
_DEFAULT_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
]

# Coin-specific keyword map for relevance filtering
_SYMBOL_KEYWORDS: dict[str, list[str]] = {
    "BTCUSDT":  ["bitcoin", "btc"],
    "ETHUSDT":  ["ethereum", "eth", "ether"],
    "SOLUSDT":  ["solana", "sol"],
    "BNBUSDT":  ["bnb", "binance coin"],
    "XRPUSDT":  ["xrp", "ripple"],
    "ADAUSDT":  ["cardano", "ada"],
    "DOGEUSDT": ["dogecoin", "doge"],
    "AVAXUSDT": ["avalanche", "avax"],
    "DOTUSDT":  ["polkadot", "dot"],
    "MATICUSDT":["polygon", "matic"],
}


def _is_relevant(item: dict, keywords: list[str]) -> bool:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return any(kw in text for kw in keywords)


def _parse_entry(entry, source_name: str) -> dict:
    published = ""
    if hasattr(entry, "published"):
        published = entry.published
    elif hasattr(entry, "updated"):
        published = entry.updated

    summary = ""
    if hasattr(entry, "summary"):
        summary = entry.summary[:300] if entry.summary else ""

    return {
        "title":        entry.get("title", ""),
        "source":       source_name,
        "published_at": published,
        "url":          entry.get("link", ""),
        "summary":      summary,
    }


class RSSFeedAdapter:
    """Fetch crypto news from public RSS feeds using httpx + feedparser.

    Returns a list of news dicts on success, or None when all feeds fail —
    the None sentinel triggers the "news_unavailable" data_gap in the collector.
    """

    source_name = "rss"

    def __init__(self, feeds: list[str] | None = None) -> None:
        self._feeds = feeds if feeds is not None else _DEFAULT_FEEDS

    async def fetch(self, symbol: str) -> Optional[list[dict]]:
        keywords = _SYMBOL_KEYWORDS.get(symbol, [symbol.replace("USDT", "").lower()])
        all_items: list[dict] = []
        any_success = False

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for url in self._feeds:
                try:
                    resp = await client.get(url, follow_redirects=True)
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.text)
                    source_name = feed.feed.get("title", url) if feed.feed else url
                    any_success = True
                    for entry in feed.entries[:20]:
                        item = _parse_entry(entry, source_name)
                        if _is_relevant(item, keywords):
                            all_items.append(item)
                except Exception as exc:
                    logger.warning("[rss] failed to fetch %s: %s", url, exc)

        if not any_success:
            return None

        # Sort by published_at descending (lexicographic works for ISO dates), cap at 10
        all_items.sort(key=lambda x: x["published_at"], reverse=True)
        return all_items[:10] or None
