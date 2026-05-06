from __future__ import annotations
from config.settings import Settings
from graph.state import AgentState


def make_risk_analyzer(settings: Settings):
    async def analyze_risk(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            pass
        return _deterministic_risk(state)
    return analyze_risk


def _deterministic_risk(state: AgentState) -> dict:
    context       = state.get("context") or {}
    price_summary = context.get("price_summary", {})
    onchain       = context.get("onchain_summary", {})
    funding       = context.get("funding_rate_summary")    # Optional[FundingRateSummary]
    data_gaps     = context.get("data_gaps", [])
    risk_factors: list[str] = []
    risk_score = 0

    change = abs(price_summary.get("change_24h_pct", 0.0))
    if change > 10:
        risk_factors.append(f"High price volatility: {change:.1f}% in 24h")
        risk_score += 2
    elif change > 5:
        risk_factors.append(f"Moderate price volatility: {change:.1f}% in 24h")
        risk_score += 1

    if onchain.get("mempool_size", 0) > 100_000:
        risk_factors.append("High mempool congestion detected")
        risk_score += 1

    if funding is not None:
        rate      = funding["rate"]
        abs_rate  = abs(rate)
        direction = "longs" if rate > 0 else "shorts"

        if abs_rate >= 0.0015:
            risk_factors.append(f"Extreme funding rate {rate:+.3%} — {direction} overextended")
            risk_score += 2
        elif abs_rate >= 0.0005:
            risk_factors.append(f"Elevated funding rate {rate:+.3%} — {direction} crowded")
            risk_score += 1

    if data_gaps:
        risk_factors.append(f"Incomplete data: {', '.join(data_gaps)}")
        risk_score += 1

    risk_level = "high" if risk_score >= 3 else "medium" if risk_score >= 1 else "low"

    return {
        "risk_analysis": {
            "risk_level":   risk_level,
            "risk_factors": risk_factors or ["No significant risk factors detected"],
        }
    }
