# API Examples

Base URL: `http://localhost:8000`

---

## GET /health

Check that the API is running and see the current mode.

**Request:**

```bash
curl http://localhost:8000/health
```

**Response (200 OK):**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "mock_mode": true,
  "llm_enabled": false
}
```

| Field | Type | Description |
|---|---|---|
| `status` | `"ok"` | Always `"ok"` when the server is healthy |
| `version` | string | API version |
| `mock_mode` | bool | `true` when using mock data (no external calls) |
| `llm_enabled` | bool | `true` when Claude AI analysis is active (Phase 9) |

---

## GET /report

Generate a market intelligence report for a symbol.

**Parameters:**

| Name | Type | Required | Constraint | Default |
|---|---|---|---|---|
| `symbol` | string | No | `^[A-Z][A-Z0-9]{2,19}$` | `BTCUSDT` |

**Request:**

```bash
curl "http://localhost:8000/report?symbol=BTCUSDT"
```

**Response (200 OK) — success:**

```json
{
  "run_id": "08ea5f97-3cef-4c37-b942-665806be4ed0",
  "symbol": "BTCUSDT",
  "requested_at": "2026-05-04T08:28:09.385788+00:00",
  "generated_at": "2026-05-04T08:28:10.577225+00:00",
  "market_bias": "bullish",
  "confidence_score": 0.65,
  "key_signals": [
    "BTC +1.65% in 24h",
    "Market structure: neutral (20% confidence)",
    "MA trend: uptrend",
    "RSI: 63",
    "Strategy takes Bitcoin buying breather ahead of Q1 earnings"
  ],
  "risk_warnings": [
    "No significant risk factors detected"
  ],
  "narrative": "BTC shows bullish bias. Market structure: neutral (20%). RSI 63, MA uptrend, sentiment neutral. Risk: low.",
  "data_gaps": [],
  "error": null,
  "llm_used": false,
  "price_source": "binance",
  "news_source": "rss",
  "analysis_engine": "rule-based",
  "market_structure": {
    "bias": "neutral",
    "rsi": 63.3,
    "ma_trend": "uptrend",
    "confidence_score": 0.2,
    "explanation": "Bias: neutral. liquidity sweep high confirmed at 79199.48",
    "swing_highs": [78514.82, 78394.0, 78596.61, 79199.48, 78878.77, 80635.51],
    "swing_lows": [78040.0, 78094.43, 78310.54],
    "liquidity_sweeps": [
      {
        "type": "high",
        "swept_level": 78394.0,
        "sweep_candle_idx": 1,
        "confirmed": true
      }
    ],
    "order_blocks": [],
    "bos_choch": [],
    "volume_confirmed": false,
    "invalidation_level": null,
    "macd_histogram_slope": -19.495049,
    "momentum_pct": -0.76,
    "ml_probability_1r": null,
    "ml_probability_2r": null
  }
}
```

**Response (200 OK) — error (price data unavailable):**

```json
{
  "run_id": "abc123",
  "symbol": "BTCUSDT",
  "requested_at": "2026-05-04T08:28:09+00:00",
  "generated_at": "2026-05-04T08:28:10+00:00",
  "error": "Price data unavailable — cannot generate intelligence report",
  "data_gaps": ["price_unavailable"]
}
```

**Response (422 Unprocessable Entity) — invalid symbol:**

```bash
curl "http://localhost:8000/report?symbol=btcusdt"
```

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["query", "symbol"],
      "msg": "String should match pattern '^[A-Z][A-Z0-9]{2,19}$'",
      "input": "btcusdt"
    }
  ]
}
```

**Response (401 Unauthorized) — when API_AUTH_ENABLED=true:**

```bash
curl "http://localhost:8000/report?symbol=BTCUSDT"
# → 401

curl "http://localhost:8000/report?symbol=BTCUSDT" -H "X-API-Key: wrong"
# → 401

curl "http://localhost:8000/report?symbol=BTCUSDT" -H "X-API-Key: your-secret"
# → 200
```

---

## GET /history

Retrieve the most recent reports for a symbol from SQLite.

**Parameters:**

| Name | Type | Required | Constraint | Default |
|---|---|---|---|---|
| `symbol` | string | No | `^[A-Z][A-Z0-9]{2,19}$` | `BTCUSDT` |
| `limit` | integer | No | 1–100 | 10 |

**Request:**

```bash
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=3"
```

**Response (200 OK):**

```json
[
  {
    "run_id": "08ea5f97-...",
    "symbol": "BTCUSDT",
    "generated_at": "2026-05-04T08:30:00+00:00",
    "market_bias": "bullish",
    "confidence_score": 0.65,
    "narrative": "BTC shows bullish bias...",
    "price_source": "binance",
    "news_source": "rss",
    "analysis_engine": "rule-based"
  },
  {
    "run_id": "17fb3c12-...",
    "symbol": "BTCUSDT",
    "generated_at": "2026-05-04T08:00:00+00:00",
    "market_bias": "neutral",
    "confidence_score": 0.52,
    "narrative": "BTC shows neutral bias...",
    "price_source": "binance",
    "news_source": "rss",
    "analysis_engine": "rule-based"
  }
]
```

Returns an empty array `[]` if no reports have been saved for the symbol yet.

**Response (422) — invalid parameters:**

```bash
curl "http://localhost:8000/history?symbol=btcusdt"   # lowercase → 422
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=101"  # limit > 100 → 422
```

---

## Interactive Docs

FastAPI generates interactive Swagger UI automatically:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## Using API Authentication

When `API_AUTH_ENABLED=true` in `.env`, all endpoints require the `X-API-Key` header:

```bash
# Without key → 401
curl "http://localhost:8000/report?symbol=BTCUSDT"

# With correct key → 200
curl "http://localhost:8000/report?symbol=BTCUSDT" \
  -H "X-API-Key: your-secret-key-here"
```

Set the key in `.env`:
```env
API_AUTH_ENABLED=true
API_KEY=your-secret-key-here
```
