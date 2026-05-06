# graph/state.py
from __future__ import annotations
import operator
from typing import Annotated, Literal, Optional, Union
from typing import TypedDict


class FundingRateSummary(TypedDict):
    rate:         float
    funding_time: str
    source:       str


class NormalizedMarketContext(TypedDict):
    """Produced by aggregate_raw. All downstream nodes read only from this."""
    symbol:               str
    price_summary:        dict
    news_items:           list[dict]
    onchain_summary:      dict
    social_summary:       dict
    data_gaps:            list[str]
    price_source:         str
    news_source:          str
    funding_rate_summary: Optional[FundingRateSummary]


class AnalysisResult(TypedDict):
    """Produced by merge_analysis. Combines three analyzer outputs."""
    sentiment_score:   Optional[float]
    sentiment_label:   Optional[str]
    sentiment_drivers: Optional[list[str]]
    market_structure:  Optional[dict]
    risk_level:        Optional[str]
    risk_factors:      Optional[list[str]]


class IntelligenceReport(TypedDict):
    """Produced by supervisor on success."""
    run_id:           str
    symbol:           str
    requested_at:     str
    generated_at:     str
    market_bias:      Literal["bullish", "bearish", "neutral"]
    confidence_score: float
    key_signals:      list[str]
    risk_warnings:    list[str]
    narrative:        str
    data_gaps:        list[str]
    error:            Optional[str]
    llm_used:         bool
    market_structure: Optional[dict]
    price_source:     str
    news_source:      str
    analysis_engine:  str
    funding_source:   str


class ErrorReport(TypedDict):
    """Produced by aggregate_raw when price_data is None."""
    run_id:       str
    symbol:       str
    requested_at: str
    generated_at: str
    error:        str
    data_gaps:    list[str]


class AgentState(TypedDict):
    # Pipeline trigger fields
    run_id:       str
    symbol:       str
    requested_at: str

    # Raw collector outputs
    price_data:        Optional[dict]
    news_data:         Annotated[list, operator.add]
    onchain_data:      Optional[dict]
    social_data:       Optional[dict]
    funding_rate_data: Optional[dict]

    # Post-aggregation context
    context: Optional[NormalizedMarketContext]

    # Independent analyzer outputs (written in parallel, never conflict)
    sentiment_analysis:        Optional[dict]
    market_structure_analysis: Optional[dict]
    risk_analysis:             Optional[dict]

    # Merged analysis (written by merge_analysis)
    analysis: Optional[AnalysisResult]

    # Final report (IntelligenceReport or ErrorReport)
    report: Optional[Union[IntelligenceReport, ErrorReport]]

    # Accumulator fields — reducer-safe for parallel writes
    data_gaps: Annotated[list[str], operator.add]
    errors:    Annotated[list[str], operator.add]
