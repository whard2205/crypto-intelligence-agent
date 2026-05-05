from __future__ import annotations
from typing import Optional
import httpx
from data_sources.base import DataSourceAdapter

_BASE = "https://api.coingecko.com/api/v3"
_TIMEOUT = 15.0

# Binance symbol → CoinGecko coin ID
_SYMBOL_MAP: dict[str, str] = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin",
    "AVAXUSDT": "avalanche-2",
    "DOTUSDT": "polkadot",
    "MATICUSDT": "matic-network",
}


class CoinGeckoPriceAdapter(DataSourceAdapter):
    """CoinGecko public REST API — free tier, no key required.

    Used as a fallback when Binance is unavailable. OHLC endpoint returns
    4-entry candles [timestamp, open, high, low, close]; volume is set to 0.0
    since CoinGecko free tier does not include per-candle volume.
    """

    source_name = "coingecko"

    async def fetch(self, symbol: str) -> Optional[dict]:
        coin_id = _SYMBOL_MAP.get(symbol)
        if coin_id is None:
            return None

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            price_resp = await client.get(
                f"{_BASE}/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_market_cap": "true",
                },
            )
            price_resp.raise_for_status()
            price_data = price_resp.json().get(coin_id, {})

            ohlc_resp = await client.get(
                f"{_BASE}/coins/{coin_id}/ohlc",
                params={"vs_currency": "usd", "days": "1"},
            )
            ohlc_resp.raise_for_status()
            ohlc_raw = ohlc_resp.json()

        ohlcv = [
            {
                "open":   float(c[1]),
                "high":   float(c[2]),
                "low":    float(c[3]),
                "close":  float(c[4]),
                "volume": 0.0,
            }
            for c in ohlc_raw
            if len(c) >= 5
        ]

        price = float(price_data.get("usd", 0.0))
        prices = [c["close"] for c in ohlcv] if ohlcv else [price]
        high_24h = max(c["high"] for c in ohlcv) if ohlcv else price
        low_24h  = min(c["low"]  for c in ohlcv) if ohlcv else price

        return {
            "symbol":         symbol,
            "price_usd":      price,
            "change_24h_pct": float(price_data.get("usd_24h_change", 0.0)),
            "volume_24h_usd": float(price_data.get("usd_24h_vol", 0.0)),
            "high_24h":       high_24h,
            "low_24h":        low_24h,
            "ohlcv_24h":      ohlcv,
            "source":         "coingecko",
        }
