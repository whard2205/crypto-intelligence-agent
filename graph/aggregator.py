from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from graph.state import AgentState, NormalizedMarketContext, AnalysisResult, FundingRateSummary


async def aggregate_raw(state: AgentState) -> dict:
    """Normalize raw collector outputs into NormalizedMarketContext.

    Critical check: if price_data is None, sets report to ErrorReport and
    route_after_aggregate will send the graph to error_exit.
    """
    price_data        = state.get("price_data")
    news_data         = state.get("news_data") or []
    onchain_data      = state.get("onchain_data")
    social_data       = state.get("social_data")
    funding_rate_data = state.get("funding_rate_data")

    if price_data is None:
        return {
            "report": {
                "run_id":       state["run_id"],
                "symbol":       state["symbol"],
                "requested_at": state["requested_at"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "error":        "Price data unavailable — cannot generate intelligence report",
                "data_gaps":    list(set(state.get("data_gaps", []))),
            }
        }

    price_summary = {
        "price":          price_data.get("price_usd", 0.0),
        "change_24h_pct": price_data.get("change_24h_pct", 0.0),
        "volume_24h":     price_data.get("volume_24h_usd", 0.0),
        "high_24h":       price_data.get("high_24h", 0.0),
        "low_24h":        price_data.get("low_24h", 0.0),
        "ohlcv_24h":      price_data.get("ohlcv_24h", []),
    }

    news_items = [
        {
            "headline":     item.get("title", ""),
            "source":       item.get("source", ""),
            "published_at": item.get("published_at", ""),
            "url":          item.get("url", ""),
        }
        for item in news_data
    ]

    social_summary: dict = {}
    if social_data:
        social_summary = {
            "mention_volume": social_data.get("post_count", 0),
            "sentiment_hint": "neutral",
            "sample_posts":   social_data.get("top_posts", []),
        }

    price_source = price_data.get("source", "unknown")

    if not news_data:
        news_source = "unknown"
    elif all(item.get("source") == "MockNews" for item in news_data):
        news_source = "mock"
    else:
        news_source = "rss"

    funding_rate_summary: Optional[FundingRateSummary]
    if funding_rate_data is not None:
        funding_rate_summary = {
            "rate":         funding_rate_data["funding_rate"],
            "funding_time": funding_rate_data.get("funding_time", ""),
            "source":       funding_rate_data.get("source", "unknown"),
        }
    else:
        funding_rate_summary = None

    all_gaps = list(set(state.get("data_gaps", [])))
    if funding_rate_summary is None and "funding_unavailable" not in all_gaps:
        all_gaps.append("funding_unavailable")

    context: NormalizedMarketContext = {
        "symbol":               state["symbol"],
        "price_summary":        price_summary,
        "news_items":           news_items,
        "onchain_summary":      onchain_data or {},
        "social_summary":       social_summary,
        "data_gaps":            all_gaps,
        "price_source":         price_source,
        "news_source":          news_source,
        "funding_rate_summary": funding_rate_summary,
    }

    return {"context": context}


def fan_out_analyzers(state: AgentState) -> dict:
    """No-op routing node. Exists so conditional_edge from aggregate_raw can
    split into three parallel analyzer edges without LangGraph conflicts."""
    return {}


def merge_analysis(state: AgentState) -> dict:
    """Combine three independent analyzer outputs into one AnalysisResult."""
    sentiment = state.get("sentiment_analysis") or {}
    ms        = state.get("market_structure_analysis") or {}
    risk      = state.get("risk_analysis") or {}

    analysis: AnalysisResult = {
        "sentiment_score":   sentiment.get("sentiment_score"),
        "sentiment_label":   sentiment.get("sentiment_label"),
        "sentiment_drivers": sentiment.get("sentiment_drivers"),
        "market_structure":  ms if ms else None,
        "risk_level":        risk.get("risk_level"),
        "risk_factors":      risk.get("risk_factors"),
    }
    return {"analysis": analysis}
