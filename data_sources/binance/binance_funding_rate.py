from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import httpx
from data_sources.base import DataSourceAdapter

_FAPI_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
_TIMEOUT  = 10.0


class BinanceFundingRateAdapter(DataSourceAdapter):
    """Fetch latest perpetual futures funding rate from Binance. No API key required."""

    source_name = "binance_funding_rate"

    async def fetch(self, symbol: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_FAPI_URL, params={"symbol": symbol, "limit": 1})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        if not data:
            return None

        item = data[0]
        funding_rate = float(item["fundingRate"])

        ts_ms = item.get("fundingTime")
        if ts_ms:
            funding_time = (
                datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
        else:
            funding_time = ""

        return {
            "symbol":       symbol,
            "funding_rate": funding_rate,
            "funding_time": funding_time,
            "source":       "binance",
        }
