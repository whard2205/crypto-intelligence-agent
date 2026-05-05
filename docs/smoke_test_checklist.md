# Smoke Test Checklist

Run through this checklist before a demo or after making significant changes. Each check should take under 30 seconds.

---

## 0. Setup

```bash
cd crypto-intelligence-agent
uv sync
```

---

## 1. pytest passes

```bash
uv run pytest -v
```

- [ ] All 73 tests pass
- [ ] 0 warnings
- [ ] No import errors

---

## 2. API starts (MOCK_MODE=true)

```bash
uv run uvicorn api.main:app --port 8000
```

- [ ] Server starts without errors
- [ ] Log shows `Application startup complete`

---

## 3. /health returns ok

```bash
curl http://localhost:8000/health
```

- [ ] Status code 200
- [ ] `"status": "ok"`
- [ ] `"mock_mode": true`
- [ ] `"llm_enabled": false`

---

## 4. /report returns a valid report

```bash
curl "http://localhost:8000/report?symbol=BTCUSDT"
```

- [ ] Status code 200
- [ ] `"error": null`
- [ ] `"market_bias"` is one of `"bullish"`, `"bearish"`, `"neutral"`
- [ ] `0.0 <= "confidence_score" <= 1.0`
- [ ] `"key_signals"` is a non-empty list
- [ ] `"narrative"` is a non-empty string
- [ ] `"llm_used": false`
- [ ] `"analysis_engine": "rule-based"`
- [ ] `"price_source": "mock"` (in MOCK_MODE=true)
- [ ] `"news_source": "mock"` (in MOCK_MODE=true)

---

## 5. /history saves and returns report

```bash
# Generate 2 reports
curl "http://localhost:8000/report?symbol=BTCUSDT"
curl "http://localhost:8000/report?symbol=BTCUSDT"

# Retrieve history
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=10"
```

- [ ] History endpoint returns a list (not empty after reports are generated)
- [ ] Reports are ordered newest-first
- [ ] Each history entry has `symbol`, `generated_at`, `market_bias`

---

## 6. API validation rejects bad input

```bash
curl "http://localhost:8000/report?symbol=btcusdt"
curl "http://localhost:8000/history?symbol=btcusdt"
curl "http://localhost:8000/history?symbol=BTCUSDT&limit=101"
```

- [ ] Lowercase symbol → 422
- [ ] Limit > 100 → 422

---

## 7. MOCK_MODE=false uses live data

Create `.env`:
```env
ENV=development
MOCK_MODE=false
LLM_ENABLED=false
```

Restart the server, then:

```bash
curl "http://localhost:8000/report?symbol=BTCUSDT"
```

- [ ] `"price_source"` is `"binance"` or `"coingecko"` (not `"mock"`)
- [ ] `"news_source"` is `"rss"` (not `"mock"`)
- [ ] Price in `market_structure` reflects current market price
- [ ] `"llm_used": false` (LLM remains disabled)
- [ ] Report completes successfully (no `"error"` field populated)

**Fallback behavior** (optional — stop network access and retry):
- [ ] If Binance fails: `"price_source"` becomes `"coingecko"`
- [ ] CoinGecko also fails (dev mode): `"price_source"` becomes `"mock"`

---

## 8. Telegram /help works

Start the Telegram bot (requires `TELEGRAM_BOT_TOKEN` in `.env`):

```bash
uv run python -m telegram_bot.main
```

- [ ] Bot starts without errors
- [ ] `/start` — welcome message appears
- [ ] `/help` — help message with `/report` instructions appears
- [ ] Message contains `BTCUSDT` example

---

## 9. Telegram /report BTCUSDT works

In the Telegram chat:

```
/report BTCUSDT
```

- [ ] Bot replies within ~5 seconds (mock mode) or ~10 seconds (live mode)
- [ ] Reply contains `BTCUSDT`
- [ ] Reply contains bias (Bullish/Bearish/Neutral) with emoji
- [ ] Reply contains RSI value
- [ ] Reply contains `Engine: rule-based`
- [ ] Reply contains `Price: mock` (or `binance`/`coingecko` in live mode)
- [ ] Reply contains `News: mock` (or `rss` in live mode)
- [ ] Report is saved to history (verify via `/history` API call)

---

## 10. LLM remains disabled

In any mode:

- [ ] `"llm_used": false` in every `/report` response
- [ ] `"analysis_engine": "rule-based"` in every `/report` response
- [ ] No `ANTHROPIC_API_KEY` errors in server logs
- [ ] No Claude API calls appear in network traffic

---

## Quick reset after failed check

```bash
# Remove the SQLite DB to start fresh
rm data/report_history.db

# Reset env to safe defaults
cp .env.example .env   # or just delete .env for MOCK_MODE=true defaults
```
