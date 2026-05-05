# Demo Guide

## Prerequisites

```bash
git clone https://github.com/syujadewa18/crypto-intelligence-agent
cd crypto-intelligence-agent
uv sync
```

---

## 1. Run with MOCK_MODE=true (zero-cost, offline)

This is the default. No `.env` file needed.

**Start the API:**

```bash
uv run uvicorn api.main:app --reload --port 8000
```

**Test it:**

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/report?symbol=BTCUSDT"
curl "http://localhost:8000/report?symbol=ETHUSDT"
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=5"
```

The response will include `"price_source": "mock"`, `"news_source": "mock"`, confirming no external calls were made.

---

## 2. Run with MOCK_MODE=false (live data)

Create a `.env` file:

```env
ENV=development
MOCK_MODE=false
LLM_ENABLED=false
```

**Start the API:**

```bash
uv run uvicorn api.main:app --reload --port 8000
```

**Test it:**

```bash
curl "http://localhost:8000/report?symbol=BTCUSDT"
```

The response will include `"price_source": "binance"` (or `"coingecko"` if Binance is rate-limited) and `"news_source": "rss"`.

**Fallback behavior** — if Binance is down, the factory automatically tries CoinGecko. If CoinGecko is also down, mock data is used (in dev/test only) and a `data_gaps` entry is added.

---

## 3. Test /report

```bash
# Default symbol
curl "http://localhost:8000/report"

# Specific symbols
curl "http://localhost:8000/report?symbol=BTCUSDT"
curl "http://localhost:8000/report?symbol=ETHUSDT"
curl "http://localhost:8000/report?symbol=SOLUSDT"

# Invalid symbol (expect 422)
curl "http://localhost:8000/report?symbol=btcusdt"
curl "http://localhost:8000/report?symbol=BTC"
```

**Expected 200 response fields:**

```json
{
  "run_id": "...",
  "symbol": "BTCUSDT",
  "market_bias": "bullish|bearish|neutral",
  "confidence_score": 0.65,
  "key_signals": ["BTC +1.65% in 24h", "..."],
  "risk_warnings": ["No significant risk factors detected"],
  "narrative": "BTC shows bullish bias...",
  "price_source": "binance|coingecko|mock",
  "news_source": "rss|mock",
  "analysis_engine": "rule-based",
  "llm_used": false,
  "data_gaps": [],
  "error": null
}
```

---

## 4. Test /history

The `/report` endpoint automatically saves every successful report to SQLite.

```bash
# Fetch up to 10 most recent reports for BTC
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=10"

# Limit to 3
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=3"

# Different symbol
curl "http://localhost:8000/history?symbol=ETHUSDT"

# limit > 100 returns 422
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=101"
```

---

## 5. Test Telegram /report

**Setup:**

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather) and copy the token
2. Get your chat ID (send a message to [@userinfobot](https://t.me/userinfobot))
3. Add to `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```
4. Start the bot:
   ```bash
   uv run python -m telegram_bot.main
   ```

**Commands:**

```
/start         — welcome message
/help          — available commands
/report BTCUSDT   — generate BTC report
/report ETHUSDT   — generate ETH report
/report SOLUSDT   — generate SOL report
```

The bot responds with a formatted HTML message showing bias, market structure, key signals, risk warnings, and data provenance.

---

## 6. Verify data sources in report

The `price_source`, `news_source`, and `analysis_engine` fields in every report confirm which adapters ran:

| Scenario | price_source | news_source |
|---|---|---|
| MOCK_MODE=true | mock | mock |
| MOCK_MODE=false, Binance up | binance | rss |
| MOCK_MODE=false, Binance down | coingecko | rss |
| MOCK_MODE=false, all live down (dev) | mock | mock |
| news gap | any | unknown |

---

## 7. Run tests

```bash
# All tests (73 total)
uv run pytest -v

# Specific test modules
uv run pytest tests/unit/test_supervisor.py -v
uv run pytest tests/unit/test_binance_adapter.py -v
uv run pytest tests/unit/test_coingecko_adapter.py -v
uv run pytest tests/unit/test_rss_feed.py -v
uv run pytest tests/integration/test_api.py -v
uv run pytest tests/integration/test_history_api.py -v
uv run pytest tests/integration/test_pipeline.py -v
```

All tests run entirely offline (mock adapters + respx HTTP mocking). No network or API keys required.
