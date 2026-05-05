# Architecture

## Overview

The system is built around a **LangGraph StateGraph** that fans out work across multiple parallel agents and merges results before producing a final `IntelligenceReport`. FastAPI and the Telegram bot live outside the graph and call it as a black box.

---

## LangGraph Pipeline

```
START
  │
  ├─► price_collector   ─┐
  ├─► news_collector    ─┤
  ├─► onchain_collector ─┤──► aggregate_raw
  └─► social_collector  ─┘         │
                              (error exit if
                               price missing)
                                    │
                              fan_out_analyzers
                                    │
                        ┌───────────┼───────────┐
                        ▼           ▼           ▼
               sentiment_  market_structure_ risk_
               analyzer    analyzer         analyzer
                        │           │           │
                        └───────────┼───────────┘
                                    ▼
                              merge_analysis
                                    │
                                    ▼
                                supervisor
                                    │
                                    ▼
                                  END
```

### State reducers

`news_data`, `data_gaps`, and `errors` use `Annotated[list, operator.add]` reducers so parallel writers can safely append without conflicts. All other fields are single-writer.

### Conditional routing

`route_after_aggregate` checks whether `aggregate_raw` returned an `ErrorReport` (price unavailable) or a valid `NormalizedMarketContext`:

- Error → `error_exit` (graph ends with error report)
- Success → `fan_out_analyzers` (continues to analysis)

---

## Collector Agents

Each collector is a simple async function that calls one data source adapter and writes its result into state.

| Collector | State field written | Adapter |
|---|---|---|
| `price_collector` | `price_data` | `price_adapter` (injected) |
| `news_collector` | `news_data` | `news_adapter` (injected) |
| `onchain_collector` | `onchain_data` | `onchain_adapter` (injected) |
| `social_collector` | `social_data` | `social_adapter` (injected) |

When a collector's adapter returns `None` or raises, the collector appends to `data_gaps` instead of writing its primary field. The pipeline continues without that data.

---

## Analyzer Agents

All three analyzers run in parallel after `fan_out_analyzers`. Each reads from `state["context"]` (the normalized market context written by `aggregate_raw`) and writes to its own dedicated field.

### Sentiment Analyzer

- Reads: `context["news_items"]`
- Writes: `sentiment_analysis` (`{sentiment_score, sentiment_label, sentiment_drivers}`)
- Logic: keyword scoring on headline text (bearish/bullish word lists); score averaged across all headlines

### Market Structure Analyzer (`agents/analyzers/market_structure_analyzer.py`)

- Reads: `context["price_summary"]["ohlcv_24h"]` (60× 1h candles)
- Writes: `market_structure_analysis`
- ICT/SMC logic:
  - **Swing detection** — local n=3 pivot highs and lows
  - **Liquidity sweeps** — price breaks a prior swing then closes back (hunt-and-return)
  - **Order blocks** — last up/down candle before a BOS move
  - **BOS/CHOCH** — Break of Structure (same direction) vs Change of Character (reversal)
  - **Volume confirmation** — BOS candle volume > rolling average
  - **Confidence scoring** — BOS +0.30, liquidity sweep +0.20, OB present +0.20, volume confirmed +0.10
  - **Indicators** — RSI(14), MACD histogram slope, MA(20) trend, momentum %

### Risk Analyzer

- Reads: `context["price_summary"]`, `context["onchain_summary"]`, `context["data_gaps"]`
- Writes: `risk_analysis` (`{risk_level, risk_factors}`)
- Logic: volatility (high/low range vs price), mempool congestion, data gap count

---

## Supervisor

The supervisor runs after `merge_analysis` and has access to the fully assembled `AnalysisResult`. It is the only node that writes the final `IntelligenceReport`.

### Vote-based market bias

```
market_structure_bias == bullish  → bull += 2
market_structure_bias == bearish  → bear += 2
sentiment_score > 0.1             → bull += 1
sentiment_score < -0.1            → bear += 1
ma_trend == uptrend               → bull += 1
ma_trend == downtrend             → bear += 1
rsi > 55                          → bull += 1
rsi < 45                          → bear += 1
momentum > 1.0%                   → bull += 1
momentum < -1.0%                  → bear += 1

bull > bear → "bullish"
bear > bull → "bearish"
else        → "neutral"
```

Market structure carries 2× weight because it uses 60 candles of OHLCV data vs single-value indicators.

### Risk consistency invariant (strict 6-step order)

1. Collect `risk_factors` from `risk_analysis`
2. Build `risk_warnings` (filter trivial; add RSI overbought/oversold if applicable)
3. Apply **Rule A**: RSI ≥ 75 + bullish bias → `risk_level` cannot be "low"
4. Apply **Rule B**: any non-trivial warning present → `risk_level` cannot be "low"
5. Write narrative **last** — always uses the final mutated `risk_level`

This ordering guarantees that the narrative's "Risk: low/medium/high" always matches the risk warnings shown.

### Confidence score

```
signal_conf = max(bull, bear) / total_votes × 0.40
base_conf   = 0.20 + signal_conf + ms_confidence × 0.25
gap_penalty = 0.05 × len(data_gaps)
confidence  = clamp(base_conf - gap_penalty, 0.10, 1.00)
```

---

## FastAPI Layer

FastAPI lives outside the graph. The `/report` endpoint:

1. Builds adapters via `data_sources/factory.py`
2. Builds the graph via `graph/pipeline.py`
3. Calls `graph.ainvoke(initial_state)`
4. If successful, saves to SQLite and returns `IntelligenceReportResponse`
5. If error, returns `ErrorReportResponse`

Authentication is optional (`API_AUTH_ENABLED`). When enabled, all endpoints require an `X-API-Key` header.

---

## Telegram Bot

The Telegram bot also lives outside the graph. The `/report` command:

1. Parses the symbol from the message text
2. Calls the same graph pipeline as the API
3. Saves the report to SQLite (shared repo)
4. Formats the report as Telegram HTML and sends it back

The bot uses `python-telegram-bot v20` (asyncio-based). Async initialization of the SQLite repo happens in the `post_init` hook.

---

## Fallback Adapter Design

`FallbackAdapter` chains multiple `DataSourceAdapter` instances. It tries each in order and returns the first non-None result. Exceptions are caught and logged; the chain continues.

```python
class FallbackAdapter(DataSourceAdapter):
    async def fetch(self, symbol: str) -> Optional[Any]:
        for adapter in self._chain:
            try:
                result = await adapter.fetch(symbol)
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning(...)
        return None
```

### Factory routing rules

```
MOCK_MODE=true              → price=Mock,  news=Mock

MOCK_MODE=false
  ENV=development/test      → price=Binance→CoinGecko→Mock
                               news=RSS→Mock

  ENV=production            → price=Binance→CoinGecko   (no mock fallback)
                               news=RSS                  (no mock fallback)
```

In production, mock adapters are never silently used. A failure surfaces as a `data_gap` rather than returning fake data.

---

## Mock Mode vs Live Mode

| Aspect | MOCK_MODE=true | MOCK_MODE=false |
|---|---|---|
| Price data | Deterministic fixture (~$65K BTC) | Binance live REST |
| News data | Hardcoded headlines | RSS feeds (CoinTelegraph, CoinDesk, Decrypt) |
| Network calls | None | Binance + CoinGecko + RSS |
| API keys required | None | None (all public APIs) |
| CI/CD safe | Yes | No (flaky on network failure) |
| `price_source` in report | `"mock"` | `"binance"` or `"coingecko"` |
| `news_source` in report | `"mock"` | `"rss"` |

---

## Report Provenance Fields

Every `IntelligenceReport` carries:

| Field | Values | Meaning |
|---|---|---|
| `price_source` | `binance`, `coingecko`, `mock`, `unknown` | Which adapter provided price data |
| `news_source` | `rss`, `mock`, `unknown` | Which adapter provided news data |
| `analysis_engine` | `rule-based` (MVP), `claude` (Phase 9) | Which analysis path ran |
| `llm_used` | `false` (MVP), `true` (Phase 9) | Whether a Claude API call was made |
| `data_gaps` | list of strings | Which data sources were unavailable |
