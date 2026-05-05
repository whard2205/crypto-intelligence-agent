from __future__ import annotations
import httpx
from data_sources.base import DataSourceAdapter

_BASE = "https://api.binance.com/api/v3"
_TIMEOUT = 10.0


class BinancePriceAdapter(DataSourceAdapter):
    """Fetch price + OHLCV from Binance public REST API. No API key required."""

    source_name = "binance"

    async def fetch(self, symbol: str) -> dict:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            ticker_resp = await client.get(
                f"{_BASE}/ticker/24hr", params={"symbol": symbol}
            )
            ticker_resp.raise_for_status()
            ticker = ticker_resp.json()

            klines_resp = await client.get(
                f"{_BASE}/klines",
                params={"symbol": symbol, "interval": "1h", "limit": 60},
            )
            klines_resp.raise_for_status()
            klines = klines_resp.json()

        ohlcv = [
            {
                "open":   float(k[1]),
                "high":   float(k[2]),
                "low":    float(k[3]),
                "close":  float(k[4]),
                "volume": float(k[5]),
            }
            for k in klines
        ]

        return {
            "symbol":          symbol,
            "price_usd":       float(ticker["lastPrice"]),
            "change_24h_pct":  float(ticker["priceChangePercent"]),
            "volume_24h_usd":  float(ticker["quoteVolume"]),
            "high_24h":        float(ticker["highPrice"]),
            "low_24h":         float(ticker["lowPrice"]),
            "ohlcv_24h":       ohlcv,
            "source":          "binance",
        }
