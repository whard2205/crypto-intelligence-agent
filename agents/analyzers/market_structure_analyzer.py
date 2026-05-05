"""Rule-based ICT/SMC market structure analyzer.

Primary signals (drive bias and confidence_score):
  swing high / swing low → liquidity sweep → order block → BOS / CHOCH → volume

Secondary indicators (confirmation only, adjust confidence_score by ≤0.05 each):
  RSI(14), MACD histogram slope, MA trend (20/50), momentum(5-bar RoC)

Phase 2: ml_probability_1r / ml_probability_2r (None until ML model trained)
Phase 3: monte_carlo (None until Monte Carlo enabled)
"""
from __future__ import annotations
import logging
import math
from typing import Optional

from graph.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public node
# ---------------------------------------------------------------------------

async def analyze_market_structure(state: AgentState) -> dict:
    context = state.get("context") or {}
    ohlcv   = context.get("price_summary", {}).get("ohlcv_24h", [])

    _empty = {
        "bias": "neutral",
        "swing_highs": [], "swing_lows": [],
        "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
        "volume_confirmed": False, "invalidation_level": None,
        "rsi": 50.0, "macd_histogram_slope": 0.0,
        "ma_trend": "sideways", "momentum_pct": 0.0,
        "confidence_score": 0.0,
        "explanation": "Insufficient OHLCV data for market structure analysis.",
        "ml_probability_1r": None, "ml_probability_2r": None,
    }

    if not ohlcv or len(ohlcv) < 10:
        return {"market_structure_analysis": _empty}

    highs   = [float(c["high"])          for c in ohlcv]
    lows    = [float(c["low"])           for c in ohlcv]
    closes  = [float(c["close"])         for c in ohlcv]
    volumes = [float(c.get("volume", 0)) for c in ohlcv]

    # --- Primary signals ---
    swing_highs  = _detect_swing_highs(highs, n=3)
    swing_lows   = _detect_swing_lows(lows, n=3)
    sweeps       = _detect_liquidity_sweeps(highs, lows, closes, swing_highs, swing_lows)
    bos_choch    = _deduplicate_bos(_detect_bos_choch(closes, swing_highs, swing_lows))
    order_blocks = _detect_order_blocks(highs, lows, closes, bos_choch)
    vol_confirmed = _volume_confirmed(volumes)
    vol_missing   = _volumes_all_zero(volumes)
    invalidation  = _invalidation_level(bos_choch, swing_highs, swing_lows)

    bias = "neutral"
    if bos_choch:
        bias = bos_choch[-1]["direction"]

    # --- Secondary indicators ---
    rsi        = _compute_rsi(closes)
    macd_slope = _compute_macd_histogram_slope(closes)
    ma20       = _sma(closes, 20)
    ma50       = _sma(closes, 50)
    ma_trend   = _ma_trend(closes[-1], ma20, ma50)
    momentum   = round((closes[-1] - closes[-5]) / closes[-5] * 100, 2) if len(closes) >= 5 else 0.0

    # --- Confidence score + explanation ---
    confidence, explanation = _score_and_explain(
        bias, bos_choch, sweeps, order_blocks, vol_confirmed,
        rsi, macd_slope, ma_trend, momentum,
        vol_data_missing=vol_missing,
    )

    return {
        "market_structure_analysis": {
            "bias":                  bias,
            "swing_highs":           swing_highs,
            "swing_lows":            swing_lows,
            "liquidity_sweeps":      sweeps,
            "order_blocks":          order_blocks,
            "bos_choch":             bos_choch,
            "volume_confirmed":      vol_confirmed,
            "invalidation_level":    invalidation,
            "rsi":                   round(rsi, 1),
            "macd_histogram_slope":  round(macd_slope, 6),
            "ma_trend":              ma_trend,
            "momentum_pct":          momentum,
            "confidence_score":      round(confidence, 2),
            "explanation":           explanation,
            "ml_probability_1r":     None,
            "ml_probability_2r":     None,
        }
    }


# ---------------------------------------------------------------------------
# Swing detection
# ---------------------------------------------------------------------------

def _detect_swing_highs(highs: list[float], n: int = 3) -> list[float]:
    result = []
    for i in range(n, len(highs) - n):
        if all(highs[i] > highs[i - j] and highs[i] > highs[i + j] for j in range(1, n + 1)):
            result.append(round(highs[i], 2))
    return result


def _detect_swing_lows(lows: list[float], n: int = 3) -> list[float]:
    result = []
    for i in range(n, len(lows) - n):
        if all(lows[i] < lows[i - j] and lows[i] < lows[i + j] for j in range(1, n + 1)):
            result.append(round(lows[i], 2))
    return result


# ---------------------------------------------------------------------------
# Liquidity sweep
# ---------------------------------------------------------------------------

def _detect_liquidity_sweeps(
    highs: list[float], lows: list[float], closes: list[float],
    swing_highs: list[float], swing_lows: list[float],
) -> list[dict]:
    sweeps: list[dict] = []
    if not swing_highs and not swing_lows:
        return sweeps

    seen_highs: set[float] = set()
    seen_lows:  set[float] = set()

    for i in range(1, len(closes)):
        for level in swing_highs:
            if level not in seen_highs and highs[i] > level and closes[i] < level:
                sweeps.append({
                    "type": "high", "swept_level": round(level, 2),
                    "sweep_candle_idx": i, "confirmed": True,
                })
                seen_highs.add(level)
                break
        for level in swing_lows:
            if level not in seen_lows and lows[i] < level and closes[i] > level:
                sweeps.append({
                    "type": "low", "swept_level": round(level, 2),
                    "sweep_candle_idx": i, "confirmed": True,
                })
                seen_lows.add(level)
                break

    return sweeps


# ---------------------------------------------------------------------------
# BOS / CHOCH
# ---------------------------------------------------------------------------

def _detect_bos_choch(
    closes: list[float],
    swing_highs: list[float],
    swing_lows:  list[float],
) -> list[dict]:
    events: list[dict] = []
    if len(closes) < 5 or not swing_highs or not swing_lows:
        return events

    # Track the running significant high/low
    ref_high  = max(swing_highs)
    ref_low   = min(swing_lows)
    prior_bias: Optional[str] = None

    for i in range(1, len(closes)):
        if closes[i] > ref_high:
            event_type = "BOS" if prior_bias == "bullish" else "CHOCH"
            events.append({
                "type":        event_type,
                "direction":   "bullish",
                "break_level": round(ref_high, 2),
                "candle_idx":  i,
            })
            prior_bias = "bullish"
            ref_high   = closes[i]

        elif closes[i] < ref_low:
            event_type = "BOS" if prior_bias == "bearish" else "CHOCH"
            events.append({
                "type":        event_type,
                "direction":   "bearish",
                "break_level": round(ref_low, 2),
                "candle_idx":  i,
            })
            prior_bias = "bearish"
            ref_low    = closes[i]

    return events


def _deduplicate_bos(events: list[dict]) -> list[dict]:
    """Remove redundant same-direction BOS/CHOCH events from the same structural move.

    Two events are merged when ALL of:
      • same direction
      • candle distance ≤ 2
      • break_level difference < 0.15% of the higher level

    Kept event: higher break_level for bullish, lower for bearish (the "better" level).
    """
    if len(events) < 2:
        return events
    result = list(events)
    i = 0
    while i < len(result) - 1:
        a, b = result[i], result[i + 1]
        if a["direction"] != b["direction"]:
            i += 1
            continue
        if b["candle_idx"] - a["candle_idx"] > 2:
            i += 1
            continue
        ref = max(a["break_level"], b["break_level"])
        if abs(b["break_level"] - a["break_level"]) / ref >= 0.0015:
            i += 1
            continue
        keep = b if (
            (a["direction"] == "bullish" and b["break_level"] >= a["break_level"]) or
            (a["direction"] == "bearish" and b["break_level"] <= a["break_level"])
        ) else a
        result[i] = keep
        result.pop(i + 1)
        # Don't advance i — re-check new result[i] against new result[i+1]
    return result


# ---------------------------------------------------------------------------
# Order blocks
# ---------------------------------------------------------------------------

def _detect_order_blocks(
    highs:     list[float],
    lows:      list[float],
    closes:    list[float],
    bos_choch: list[dict],
) -> list[dict]:
    blocks: list[dict] = []
    for event in bos_choch:
        idx       = event["candle_idx"]
        direction = event["direction"]
        search_start = max(1, idx - 5)

        for j in range(idx - 1, search_start - 1, -1):
            if j == 0:
                continue
            is_opposing = (
                (direction == "bullish" and closes[j] < closes[j - 1]) or
                (direction == "bearish" and closes[j] > closes[j - 1])
            )
            if is_opposing:
                mitigated = (
                    any(lows[k] <= lows[j] for k in range(idx, len(lows)))
                    if direction == "bullish"
                    else any(highs[k] >= highs[j] for k in range(idx, len(highs)))
                )
                blocks.append({
                    "type":       direction,
                    "zone_high":  round(highs[j], 2),
                    "zone_low":   round(lows[j], 2),
                    "candle_idx": j,
                    "mitigated":  mitigated,
                })
                break

    return blocks


# ---------------------------------------------------------------------------
# Volume confirmation
# ---------------------------------------------------------------------------

def _volume_confirmed(volumes: list[float]) -> bool:
    if len(volumes) < 5:
        return False
    avg_prev = sum(volumes[:-1]) / (len(volumes) - 1)
    return volumes[-1] > avg_prev * 1.10


def _volumes_all_zero(volumes: list[float]) -> bool:
    return len(volumes) > 0 and all(v == 0.0 for v in volumes)


# ---------------------------------------------------------------------------
# Invalidation level
# ---------------------------------------------------------------------------

def _invalidation_level(
    bos_choch:   list[dict],
    swing_highs: list[float],
    swing_lows:  list[float],
) -> Optional[float]:
    if not bos_choch:
        return None
    last = bos_choch[-1]
    if last["direction"] == "bullish":
        return round(min(swing_lows), 2) if swing_lows else None
    return round(max(swing_highs), 2) if swing_highs else None


# ---------------------------------------------------------------------------
# Secondary indicators
# ---------------------------------------------------------------------------

def _compute_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas   = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains    = [max(d, 0.0) for d in deltas[-period:]]
    losses   = [-min(d, 0.0) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2.0 / (period + 1)
    result = values[0]
    for v in values[1:]:
        result = v * k + result * (1 - k)
    return result


def _compute_macd_histogram_slope(closes: list[float]) -> float:
    if len(closes) < 27:
        return 0.0
    macd_curr = _ema(closes, 12) - _ema(closes, 26)
    macd_prev = _ema(closes[:-1], 12) - _ema(closes[:-1], 26)
    return macd_curr - macd_prev


def _sma(values: list[float], period: int) -> float:
    tail = values[-min(period, len(values)):]
    return sum(tail) / len(tail) if tail else 0.0


def _ma_trend(price: float, ma20: float, ma50: float) -> str:
    if price > ma20 and ma20 > ma50:
        return "uptrend"
    if price < ma20 and ma20 < ma50:
        return "downtrend"
    return "sideways"


# ---------------------------------------------------------------------------
# Confidence score + explanation
# ---------------------------------------------------------------------------

def _score_and_explain(
    bias:             str,
    bos_choch:        list[dict],
    sweeps:           list[dict],
    order_blocks:     list[dict],
    vol_confirmed:    bool,
    rsi:              float,
    macd_slope:       float,
    ma_trend:         str,
    momentum_pct:     float,
    vol_data_missing: bool = False,
) -> tuple[float, str]:
    score = 0.0
    parts: list[str] = []

    if bos_choch:
        score += 0.30
        last = bos_choch[-1]
        parts.append(f"{last['type']} {last['direction']} at {last['break_level']:.2f}")

    confirmed_sweeps = [s for s in sweeps if s["confirmed"]]
    if confirmed_sweeps:
        score += 0.20
        last_sweep = confirmed_sweeps[-1]
        parts.append(f"liquidity sweep {last_sweep['type']} confirmed at {last_sweep['swept_level']:.2f}")

    active_obs = [ob for ob in order_blocks if not ob["mitigated"]]
    if active_obs:
        score += 0.20
        ob = active_obs[-1]
        parts.append(f"order block {ob['type']} zone {ob['zone_low']:.2f}–{ob['zone_high']:.2f}")

    if vol_confirmed:
        score += 0.10
        parts.append("volume confirms last move")
    elif vol_data_missing:
        parts.append("volume data unavailable")

    # Secondary: each worth up to 0.05
    if (bias == "bullish" and rsi > 50) or (bias == "bearish" and rsi < 50):
        score += 0.05
        parts.append(f"RSI {rsi:.0f} aligned")

    if (bias == "bullish" and macd_slope > 0) or (bias == "bearish" and macd_slope < 0):
        score += 0.05
        parts.append("MACD histogram aligned")

    trend_map = {"uptrend": "bullish", "downtrend": "bearish"}
    if trend_map.get(ma_trend) == bias:
        score += 0.05
        parts.append(f"MA trend {ma_trend}")

    if (bias == "bullish" and momentum_pct > 0) or (bias == "bearish" and momentum_pct < 0):
        score += 0.05
        parts.append(f"momentum {momentum_pct:+.2f}%")

    score = round(min(1.0, score), 2)
    explanation = (
        f"Bias: {bias}. " + " | ".join(parts)
        if parts else f"Bias: {bias}. No significant structure detected."
    )
    return score, explanation
