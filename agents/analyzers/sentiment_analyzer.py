from __future__ import annotations
from config.settings import Settings
from graph.state import AgentState

_POSITIVE = frozenset({
    "bullish", "surge", "rally", "gain", "up", "rise", "high", "buy",
    "accumulation", "strong", "moon", "pump", "breakout", "bull",
})
_NEGATIVE = frozenset({
    "bearish", "crash", "drop", "fall", "down", "sell", "low", "fear",
    "dump", "weak", "correction", "breakdown", "bear", "loss",
})


def make_sentiment_analyzer(settings: Settings):
    async def analyze_sentiment(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            # Phase 9: Claude path (not implemented in MVP)
            pass
        return _deterministic_sentiment(state)
    return analyze_sentiment


def _deterministic_sentiment(state: AgentState) -> dict:
    context    = state.get("context") or {}
    news_items = context.get("news_items", [])
    social     = context.get("social_summary", {})

    score = 0.0
    for item in news_items[:5]:
        words = set(item.get("headline", "").lower().split())
        pos   = len(words & _POSITIVE)
        neg   = len(words & _NEGATIVE)
        score += (pos - neg) * 0.15

    hint = social.get("sentiment_hint", "neutral")
    if hint == "bullish":
        score += 0.10
    elif hint == "bearish":
        score -= 0.10

    score = max(-1.0, min(1.0, round(score, 2)))
    label = "bullish" if score > 0.1 else "bearish" if score < -0.1 else "neutral"

    return {
        "sentiment_analysis": {
            "sentiment_score":   score,
            "sentiment_label":   label,
            "sentiment_drivers": [
                item["headline"] for item in news_items[:3] if item.get("headline")
            ],
        }
    }
