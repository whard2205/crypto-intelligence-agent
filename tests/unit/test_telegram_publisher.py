import pytest
from publishers.telegram_publisher import format_intelligence_report, format_error_report


def _full_report(**overrides) -> dict:
    report = {
        "run_id":           "test-run-001",
        "symbol":           "BTCUSDT",
        "requested_at":     "2026-05-04T02:00:00+00:00",
        "generated_at":     "2026-05-04T02:00:01+00:00",
        "market_bias":      "bullish",
        "confidence_score": 0.80,
        "key_signals": [
            "BTC +2.30% in 24h",
            "BOS bullish @ 65100.00",
            "Market structure: bullish (80% confidence)",
            "MA trend: uptrend",
            "RSI: 73",
        ],
        "risk_warnings": ["RSI overbought — pullback risk elevated"],
        "narrative":    "BTC shows bullish bias. Market structure: bullish (80%). RSI 73, MA uptrend.",
        "data_gaps":    [],
        "error":        None,
        "llm_used":     False,
        "market_structure": {
            "bias":            "bullish",
            "rsi":             72.9,
            "ma_trend":        "uptrend",
            "confidence_score": 1.0,
            "explanation":     "BOS bullish at 65100",
            "swing_highs":     [65100.0],
            "swing_lows":      [63900.0],
            "liquidity_sweeps": [],
            "order_blocks":    [],
            "bos_choch": [
                {"type": "BOS", "direction": "bullish",
                 "break_level": 65100.0, "candle_idx": 25}
            ],
            "volume_confirmed":    True,
            "invalidation_level":  63900.0,
            "macd_histogram_slope": 0.002,
            "momentum_pct":        1.2,
            "ml_probability_1r":   None,
            "ml_probability_2r":   None,
        },
    }
    report.update(overrides)
    return report


# ---------------------------------------------------------------------------
# 1. Basic bullish report rendering
# ---------------------------------------------------------------------------

def test_format_bullish_report():
    msg = format_intelligence_report(_full_report())
    assert "BTCUSDT" in msg
    assert "bullish" in msg.lower()
    assert "80%" in msg
    assert "Confidence" in msg


# ---------------------------------------------------------------------------
# 2. Market structure section present
# ---------------------------------------------------------------------------

def test_format_includes_market_structure():
    msg = format_intelligence_report(_full_report())
    assert "Market Structure" in msg
    assert "RSI" in msg
    assert "uptrend" in msg
    # BOS event should appear
    assert "BOS" in msg
    assert "65100" in msg


# ---------------------------------------------------------------------------
# 3. Data gaps section rendered when present
# ---------------------------------------------------------------------------

def test_format_data_gaps_shown():
    report = _full_report(data_gaps=["social_unavailable", "onchain_unavailable"])
    msg = format_intelligence_report(report)
    assert "social_unavailable" in msg
    assert "onchain_unavailable" in msg


# ---------------------------------------------------------------------------
# 4. Error report path
# ---------------------------------------------------------------------------

def test_format_error_report():
    error_report = {
        "run_id":        "err-001",
        "symbol":        "BTCUSDT",
        "requested_at":  "2026-05-04T02:00:00+00:00",
        "generated_at":  "2026-05-04T02:00:01+00:00",
        "error":         "Price data unavailable — cannot generate intelligence report",
        "data_gaps":     [],
    }
    msg = format_intelligence_report(error_report)
    assert "Error" in msg
    assert "Price data unavailable" in msg
    assert "BTCUSDT" in msg
    # Should NOT contain fields that only appear on success
    assert "Market Structure" not in msg
    assert "Key Signals" not in msg


# ---------------------------------------------------------------------------
# 5. Timezone conversion produces different output for different zones
# ---------------------------------------------------------------------------

def test_format_uses_display_timezone():
    report    = _full_report()
    msg_jakarta = format_intelligence_report(report, tz_name="Asia/Jakarta")  # UTC+7
    msg_utc     = format_intelligence_report(report, tz_name="UTC")
    # Timestamps must differ (02:00 UTC → 09:00 WIB)
    assert msg_jakarta != msg_utc
    assert "WIB" in msg_jakarta or "09:00" in msg_jakarta


# ---------------------------------------------------------------------------
# 6. /help command handler replies with help text
# ---------------------------------------------------------------------------

async def test_help_handler():
    from unittest.mock import AsyncMock, MagicMock
    from telegram_bot.main import help_command

    update          = MagicMock()
    update.message.reply_text = AsyncMock()
    context         = MagicMock()

    await help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    sent_text = update.message.reply_text.call_args[0][0]
    assert "/report" in sent_text
    assert "BTCUSDT" in sent_text
