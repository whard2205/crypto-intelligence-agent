from __future__ import annotations
from datetime import datetime, timezone
from config.settings import Settings
from graph.state import AgentState, IntelligenceReport

# Warnings that carry no real risk signal — do not trigger a risk_level upgrade.
_TRIVIAL_WARNINGS = frozenset({"No significant risk factors detected"})


def make_supervisor(settings: Settings):
    async def supervisor(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            # Phase 9: Claude path (not implemented in MVP)
            pass
        return _deterministic_supervisor(state)
    return supervisor


def _deterministic_supervisor(state: AgentState) -> dict:
    analysis = state.get("analysis") or {}
    context  = state.get("context") or {}

    sentiment_score = analysis.get("sentiment_score") or 0.0
    sentiment_label = analysis.get("sentiment_label") or "neutral"
    ms              = analysis.get("market_structure") or {}
    risk_level      = analysis.get("risk_level") or "medium"
    risk_factors    = list(analysis.get("risk_factors") or [])
    data_gaps       = list(context.get("data_gaps") or [])

    rsi           = ms.get("rsi", 50.0)
    ma_trend      = ms.get("ma_trend", "sideways")
    momentum      = ms.get("momentum_pct", 0.0)
    ms_bias       = ms.get("bias", "neutral")
    ms_confidence = ms.get("confidence_score", 0.0)

    # ------------------------------------------------------------------
    # 1. Vote-based market bias (market structure carries 2× weight)
    # ------------------------------------------------------------------
    bull, bear = 0, 0

    if ms_bias == "bullish":
        bull += 2
    elif ms_bias == "bearish":
        bear += 2

    if sentiment_score > 0.1:
        bull += 1
    elif sentiment_score < -0.1:
        bear += 1

    if ma_trend == "uptrend":
        bull += 1
    elif ma_trend == "downtrend":
        bear += 1

    if rsi > 55:
        bull += 1
    elif rsi < 45:
        bear += 1

    if momentum > 1.0:
        bull += 1
    elif momentum < -1.0:
        bear += 1

    market_bias: str
    if bull > bear:
        market_bias = "bullish"
    elif bear > bull:
        market_bias = "bearish"
    else:
        market_bias = "neutral"

    # ------------------------------------------------------------------
    # 2. Confidence score
    # ------------------------------------------------------------------
    total       = bull + bear
    signal_conf = (max(bull, bear) / total * 0.4) if total > 0 else 0.0
    base_conf   = 0.20 + signal_conf + ms_confidence * 0.25
    gap_penalty = 0.05 * len(data_gaps)
    confidence  = round(max(0.10, min(1.0, base_conf - gap_penalty)), 2)

    # ------------------------------------------------------------------
    # 3. Key signals
    # ------------------------------------------------------------------
    price_summary = context.get("price_summary", {})
    coin   = state["symbol"].replace("USDT", "")
    change = price_summary.get("change_24h_pct", 0.0)

    key_signals: list[str] = []
    if change is not None:
        key_signals.append(f"{coin} {'+' if change >= 0 else ''}{change:.2f}% in 24h")
    if ms.get("bos_choch"):
        last_event = ms["bos_choch"][-1]
        key_signals.append(
            f"{last_event['type']} {last_event['direction']} "
            f"@ {last_event['break_level']:.2f}"
        )
    if ms_confidence > 0:
        key_signals.append(
            f"Market structure: {ms_bias} ({ms_confidence:.0%} confidence)"
        )
    if ma_trend in ("uptrend", "downtrend"):
        key_signals.append(f"MA trend: {ma_trend}")
    key_signals.append(f"RSI: {rsi:.0f}")

    # Funding rate key signal
    funding = context.get("funding_rate_summary")
    if funding is not None and abs(funding["rate"]) >= 0.0005:
        direction = "longs" if funding["rate"] > 0 else "shorts"
        key_signals.append(f"Funding rate {funding['rate']:+.3%} ({direction} crowded)")

    drivers = analysis.get("sentiment_drivers") or []
    key_signals.extend(drivers[:1])

    # Funding source provenance
    funding_source = funding["source"] if funding is not None else "unavailable"

    # ------------------------------------------------------------------
    # 4. Risk warnings — built before any risk_level adjustment so the
    #    consistency check below sees the full picture.
    # ------------------------------------------------------------------
    risk_warnings: list[str] = [
        f for f in risk_factors
        if f != "No significant risk factors detected"
    ][:3]

    if rsi >= 70:
        risk_warnings.append("RSI overbought — pullback risk elevated")
    elif rsi <= 30:
        risk_warnings.append("RSI oversold — reversal risk elevated")

    if not risk_warnings:
        risk_warnings = ["No significant risk factors detected"]

    # ------------------------------------------------------------------
    # 5. Risk level — all mutations happen here, after warnings are known.
    #
    #    Rule A: RSI ≥ 75 + bullish → at least medium (directional rule).
    #    Rule B: any non-trivial warning present → must not say "low"
    #            (consistency rule — covers RSI 70-74 and other warnings).
    # ------------------------------------------------------------------
    if rsi >= 75 and market_bias == "bullish":
        if risk_level == "low":
            risk_level = "medium"

    if any(w not in _TRIVIAL_WARNINGS for w in risk_warnings):
        if risk_level == "low":
            risk_level = "medium"

    # ------------------------------------------------------------------
    # 6. Narrative — written last so it always reflects the final risk_level.
    # ------------------------------------------------------------------
    rsi_note = ""
    if rsi >= 70:
        rsi_note = ", pullback risk"
    elif rsi <= 30:
        rsi_note = ", reversal risk"

    narrative = (
        f"{coin} shows {market_bias} bias. "
        f"Market structure: {ms_bias} ({ms_confidence:.0%}). "
        f"RSI {rsi:.0f}{rsi_note}, MA {ma_trend}, sentiment {sentiment_label}. "
        f"Risk: {risk_level}."
    )
    if data_gaps:
        narrative += f" Limited data: {', '.join(data_gaps)}."

    report: IntelligenceReport = {
        "run_id":           state["run_id"],
        "symbol":           state["symbol"],
        "requested_at":     state["requested_at"],
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "market_bias":      market_bias,
        "confidence_score": confidence,
        "key_signals":      key_signals[:6] or ["Insufficient signal data"],
        "risk_warnings":    risk_warnings[:5],
        "narrative":        narrative,
        "data_gaps":        data_gaps,
        "error":            None,
        "llm_used":         False,
        "market_structure": ms if ms.get("bias") else None,
        "price_source":     context.get("price_source", "unknown"),
        "news_source":      context.get("news_source", "unknown"),
        "analysis_engine":  "rule-based",
        "funding_source":   funding_source,
    }
    return {"report": report}
