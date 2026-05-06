from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

from publishers.base import ReportPublisher

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _html(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _utc_to_local(iso_str: str, tz_name: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone(ZoneInfo(tz_name))
        return local_dt.strftime("%d %b %Y %H:%M %Z")
    except Exception:
        return iso_str


def _utc_to_local_short(iso_str: str, tz_name: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone(ZoneInfo(tz_name))
        return local_dt.strftime("%d %b %H:%M")
    except Exception:
        return iso_str


_BIAS_ARROW = {"bullish": "↑", "bearish": "↓", "neutral": "→"}
_BIAS_EMOJI = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}


# ---------------------------------------------------------------------------
# Public formatters
# ---------------------------------------------------------------------------

def format_error_report(report: dict, tz_name: str = "Asia/Jakarta") -> str:
    symbol       = _html(report.get("symbol", "?"))
    generated_at = _utc_to_local(report.get("generated_at", ""), tz_name)
    error        = _html(report.get("error", "Unknown error"))

    lines = [
        "📊 <b>Crypto Intelligence — Error</b>",
        f"<b>{symbol}</b> | {generated_at}",
        "",
        f"❌ <b>Error:</b> {error}",
    ]
    gaps = report.get("data_gaps") or []
    if gaps:
        lines.append(f"<i>Data gaps: {_html(', '.join(gaps))}</i>")
    return "\n".join(lines)


def format_intelligence_report(report: dict, tz_name: str = "Asia/Jakarta") -> str:
    """Format an IntelligenceReport or ErrorReport dict as a Telegram HTML message."""
    if report.get("error"):
        return format_error_report(report, tz_name)

    symbol       = _html(report.get("symbol", "?"))
    generated_at = _utc_to_local(report.get("generated_at", ""), tz_name)
    bias         = report.get("market_bias", "neutral")
    conf         = report.get("confidence_score", 0.0)

    arrow = _BIAS_ARROW.get(bias, "→")
    emoji = _BIAS_EMOJI.get(bias, "🟡")

    lines = [
        "📊 <b>Crypto Intelligence Report</b>",
        f"<b>{symbol}</b> | {generated_at}",
        "",
        f"{emoji} <b>Bias:</b> {arrow} {bias.capitalize()}  |  "
        f"<b>Confidence:</b> {conf:.0%}",
    ]

    # Market structure compact summary
    ms = report.get("market_structure") or {}
    if ms:
        rsi      = ms.get("rsi", 0.0)
        ma       = ms.get("ma_trend", "—")
        ms_conf  = ms.get("confidence_score", 0.0)
        bos_list = ms.get("bos_choch") or []
        last_bos = bos_list[-1] if bos_list else None
        bos_str  = (
            f"{last_bos['type']} {last_bos['direction']} "
            f"@ {last_bos['break_level']:.2f}"
            if last_bos else "—"
        )
        lines += [
            "",
            "<b>Market Structure:</b>",
            f"  • RSI: {rsi:.1f}  |  MA: {ma}  |  MS conf: {ms_conf:.0%}",
            f"  • Last event: {_html(bos_str)}",
        ]
        inv = ms.get("invalidation_level")
        if inv:
            lines.append(f"  • Invalidation: {inv:.2f}")

    # Key signals
    key_signals = report.get("key_signals") or []
    if key_signals:
        lines += ["", "<b>Key Signals:</b>"]
        for sig in key_signals:
            lines.append(f"  • {_html(sig)}")

    # Risk warnings
    risk_warnings = report.get("risk_warnings") or []
    if risk_warnings:
        lines += ["", "<b>Risk Warnings:</b>"]
        for warn in risk_warnings:
            lines.append(f"  ⚠ {_html(warn)}")

    # Narrative
    narrative = _html(report.get("narrative") or "")
    if narrative:
        lines += ["", "<b>Analysis:</b>", narrative]

    # Data gaps
    gaps = report.get("data_gaps") or []
    if gaps:
        lines += ["", f"<i>⚡ Limited data: {_html(', '.join(gaps))}</i>"]

    # Footer — provenance
    llm_used     = report.get("llm_used", False)
    engine_label = "Claude AI" if llm_used else "rule-based"
    price_src    = report.get("price_source", "unknown")
    news_src     = report.get("news_source", "unknown")
    funding_src  = report.get("funding_source", "unavailable")
    lines += [
        "",
        f"<i>Engine: {engine_label}  |  Price: {price_src}  |  "
        f"News: {news_src}  |  Funding: {funding_src}</i>",
    ]

    return "\n".join(lines)


def format_history_summary(symbol: str, records: list[dict], tz_name: str) -> str:
    """Compact multi-line history summary for one symbol. Returns HTML for parse_mode='HTML'."""
    if not records:
        return f"<i>Tidak ada history untuk {_html(symbol)}.</i>"

    lines = [f"📊 <b>{_html(symbol)}</b> — {len(records)} laporan terakhir", ""]

    for r in records:
        ts    = _utc_to_local_short(r.get("generated_at", ""), tz_name)
        bias  = r.get("market_bias", "neutral")
        emoji = _BIAS_EMOJI.get(bias, "🟡")
        conf  = r.get("confidence_score")
        conf_s = f"{conf:.2f}" if conf is not None else "—"

        signals      = r.get("key_signals") or []
        bias_changed = any(str(s).startswith("Bias changed:") for s in signals)
        change_str   = "↗ bias berubah" if bias_changed else "—"

        lines.append(f"📅 {ts} | {emoji} {bias.capitalize()} | conf: {conf_s} | {change_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Publisher class (used by scheduler in Phase 6)
# ---------------------------------------------------------------------------

class TelegramPublisher(ReportPublisher):
    """Sends a formatted intelligence report to a Telegram chat."""

    def __init__(self, bot: object, chat_id: str, tz_name: str = "Asia/Jakarta") -> None:
        self._bot     = bot
        self._chat_id = chat_id
        self._tz_name = tz_name

    async def publish(self, report: dict) -> None:
        msg = format_intelligence_report(report, self._tz_name)
        await self._bot.send_message(  # type: ignore[attr-defined]
            chat_id=self._chat_id,
            text=msg,
            parse_mode="HTML",
        )
