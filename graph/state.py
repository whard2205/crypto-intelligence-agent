from __future__ import annotations
import operator
from typing import Annotated, Literal, Optional, Union
from typing import TypedDict


class NormalizedMarketContext(TypedDict):
    """Produced by aggregate_raw. All downstream nodes read only from this."""
    symbol:          str
    price_summary:   dict   # {price, change_24h_pct, volume_24h, high_24h, low_24h, ohlcv_24h}
    news_items:      list[dict]   # [{headline, source, published_at, url}]
    onchain_summary: dict
    social_summary:  dict   # {mention_volume, sentiment_hint, sample_posts}
    data_gaps:       list[str]
    price_source:    str    # binance | coingecko | mock | unknown
    news_source:     str    # rss | mock | unknown


class AnalysisResult(TypedDict):
    """Produced by merge_analysis. Combines three analyzer outputs."""
    sentiment_score:   Optional[float]
    sentiment_label:   Optional[str]
    sentiment_drivers: Optional[list[str]]
    market_structure:  Optional[dict]   # full MarketStructureAnalysis dict
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
    error:            Optional[str]    # always None on success; present for unified API schema
    llm_used:         bool
    market_structure: Optional[dict]   # full MarketStructureAnalysis dict
    price_source:     str              # binance | coingecko | mock | unknown
    news_source:      str              # rss | mock | unknown
    analysis_engine:  str              # rule-based | claude (future)


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
    price_data:   Optional[dict]
    news_data:    Annotated[list, operator.add]   # reducer-safe: collectors append
    onchain_data: Optional[dict]
    social_data:  Optional[dict]

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
