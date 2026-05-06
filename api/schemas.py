from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    version: str
    mock_mode: bool
    llm_enabled: bool


class MarketStructureResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bias: Literal["bullish", "bearish", "neutral"]
    rsi: float
    ma_trend: Literal["uptrend", "downtrend", "sideways"]
    confidence_score: float
    explanation: str
    swing_highs: list[float] = []
    swing_lows: list[float] = []
    liquidity_sweeps: list[dict] = []
    order_blocks: list[dict] = []
    bos_choch: list[dict] = []
    volume_confirmed: bool = False
    invalidation_level: Optional[float] = None
    macd_histogram_slope: float = 0.0
    momentum_pct: float = 0.0
    ml_probability_1r: Optional[float] = None
    ml_probability_2r: Optional[float] = None


class IntelligenceReportResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    symbol: str
    requested_at: str
    generated_at: str
    market_bias: Literal["bullish", "bearish", "neutral"]
    confidence_score: float
    key_signals: list[str]
    risk_warnings: list[str]
    narrative: str
    data_gaps: list[str]
    error: Optional[str] = None
    llm_used: bool
    market_structure: Optional[MarketStructureResponse] = None
    price_source: str = "unknown"
    news_source: str = "unknown"
    analysis_engine: str = "rule-based"
    funding_source: str = "unavailable"    # new


class ErrorReportResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    symbol: str
    requested_at: str
    generated_at: str
    error: str
    data_gaps: list[str]
