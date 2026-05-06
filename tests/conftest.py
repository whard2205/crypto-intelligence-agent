import uuid
from datetime import datetime, timezone
import pytest
from config.settings import Settings


@pytest.fixture
def settings_mock() -> Settings:
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


def make_state(symbol: str = "BTCUSDT", **overrides) -> dict:
    base = {
        "run_id":       str(uuid.uuid4()),
        "symbol":       symbol,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data":   None,
        "news_data":    [],
        "onchain_data": None,
        "social_data":  None,
        "funding_rate_data": None,
        "context":      None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":     None,
        "report":       None,
        "data_gaps":    [],
        "errors":       [],
    }
    return {**base, **overrides}


def make_ohlcv(n: int = 30, base: float = 65000.0) -> list[dict]:
    """Generate minimal deterministic OHLCV for unit tests."""
    import math
    candles = []
    for i in range(n):
        close = base + i * 40 + 300 * math.sin(i * math.pi / 10)
        open_ = close - 20
        candles.append({
            "open":   round(open_, 2),
            "high":   round(max(open_, close) + 150, 2),
            "low":    round(min(open_, close) - 150, 2),
            "close":  round(close, 2),
            "volume": 900_000 + i * 5000,
            "timestamp": f"2026-05-03T{i % 24:02d}:00:00Z",
        })
    return candles
