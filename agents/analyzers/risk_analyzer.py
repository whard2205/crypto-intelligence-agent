from __future__ import annotations
from config.settings import Settings
from graph.state import AgentState


def make_risk_analyzer(settings: Settings):
    async def analyze_risk(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            # Phase 9: Claude path (not implemented in MVP)
            pass
        return _deterministic_risk(state)
    return analyze_risk


def _deterministic_risk(state: AgentState) -> dict:
    context       = state.get("context") or {}
    price_summary = context.get("price_summary", {})
    onchain       = context.get("onchain_summary", {})
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

    # RSI-based risk warnings are applied in the supervisor after all analyzers
    # merge (market_structure_analysis is not yet available during parallel execution).

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
