import pytest
from publishers.telegram_publisher import format_history_summary


def _make_record(
    bias: str = "bullish",
    conf: float | None = 0.82,
    signals: list | None = None,
    generated_at: str = "2026-05-06T07:30:00+00:00",
) -> dict:
    return {
        "symbol": "BTCUSDT",
        "market_bias": bias,
        "confidence_score": conf,
        "key_signals": signals if signals is not None else [],
        "generated_at": generated_at,
    }


def test_single_entry_bias_changed():
    record = _make_record(signals=["Bias changed: bearish → bullish"])
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    assert "↗ bias berubah" in result


def test_single_entry_no_bias_change():
    record = _make_record()
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    assert "↗ bias berubah" not in result
    lines = [l for l in result.splitlines() if "📅" in l]
    assert lines[0].endswith("| —")


def test_multiple_entries_rendered():
    records = [
        _make_record(generated_at="2026-05-06T07:30:00+00:00"),
        _make_record(generated_at="2026-05-06T03:00:00+00:00"),
        _make_record(generated_at="2026-05-05T15:15:00+00:00"),
    ]
    result = format_history_summary("BTCUSDT", records, "Asia/Jakarta")
    assert result.count("📅") == 3


def test_empty_records_returns_no_history_message():
    result = format_history_summary("BTCUSDT", [], "Asia/Jakarta")
    assert "tidak ada history" in result.lower()


def test_confidence_none_does_not_crash():
    record = _make_record(conf=None)
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    assert "—" in result


def test_timestamp_formatted_to_timezone():
    # UTC 00:00:00 → WIB (UTC+7) = 07:00
    record = _make_record(generated_at="2026-05-06T00:00:00+00:00")
    result = format_history_summary("BTCUSDT", [record], "Asia/Jakarta")
    assert "07:00" in result
