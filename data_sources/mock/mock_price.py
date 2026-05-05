from __future__ import annotations
import math
from data_sources.base import DataSourceAdapter

_CONFIGS: dict[str, dict] = {
    "BTCUSDT": {"price": 65_230.0, "change": 2.34, "vol": 28_400_000_000.0,
                "high": 66_800.0, "low": 63_900.0, "mcap": 1_285_000_000_000.0},
    "ETHUSDT": {"price": 3_185.0,  "change": 1.82, "vol": 12_100_000_000.0,
                "high": 3_260.0,  "low": 3_080.0, "mcap": 383_000_000_000.0},
    "SOLUSDT": {"price": 172.50,   "change": 3.14, "vol": 3_200_000_000.0,
                "high": 178.0,    "low": 165.0,   "mcap": 75_000_000_000.0},
    "BNBUSDT": {"price": 582.0,    "change": 0.91, "vol": 1_900_000_000.0,
                "high": 591.0,    "low": 573.0,   "mcap": 85_000_000_000.0},
}
_DEFAULT = {"price": 100.0, "change": 0.5, "vol": 500_000_000.0,
            "high": 102.0, "low": 98.0, "mcap": 1_000_000_000.0}


def _make_ohlcv(base_price: float, n: int = 60) -> list[dict]:
    """Generate n hourly candles with a trending + oscillating structure.

    Designed to produce:
    - Clear swing highs and swing lows (n=3 detection)
    - At least one BOS event
    - Volume confirmation on trend bars
    """
    candles: list[dict] = []
    start = base_price * 0.96

    for i in range(n):
        # Uptrend with two overlapping oscillation cycles
        trend = (i / n) * base_price * 0.065
        cycle_major = base_price * 0.014 * math.sin(i * 2 * math.pi / 18)
        cycle_minor = base_price * 0.005 * math.sin(i * 2 * math.pi / 6)

        close = start + trend + cycle_major + cycle_minor
        open_ = close - base_price * 0.003 * math.sin(i * 1.7)

        wick = base_price * 0.006 * (1 + 0.4 * abs(math.sin(i * 0.9)))
        high = max(open_, close) + wick
        low  = min(open_, close) - wick

        # Higher volume on strong trend bars
        vol_mult = 1.0 + 0.6 * abs(cycle_major) / (base_price * 0.014)
        volume = base_price * 22 * vol_mult

        candles.append({
            "open":      round(open_, 2),
            "high":      round(high, 2),
            "low":       round(low, 2),
            "close":     round(close, 2),
            "volume":    round(volume),
            "timestamp": f"2026-05-{3 + i // 24:02d}T{i % 24:02d}:00:00Z",
        })

    return candles


class MockPriceAdapter(DataSourceAdapter):
    source_name = "mock_price"

    async def fetch(self, symbol: str) -> dict:
        cfg = _CONFIGS.get(symbol, _DEFAULT)
        return {
            "symbol":          symbol,
            "price_usd":       cfg["price"],
            "change_24h_pct":  cfg["change"],
            "volume_24h_usd":  cfg["vol"],
            "high_24h":        cfg["high"],
            "low_24h":         cfg["low"],
            "market_cap_usd":  cfg["mcap"],
            "ohlcv_24h":       _make_ohlcv(cfg["price"]),
            "source":          "mock",
        }
