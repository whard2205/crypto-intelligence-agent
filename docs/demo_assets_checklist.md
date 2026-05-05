# Demo Assets Checklist

Screenshots to capture before publishing to GitHub/portfolio.
Save all images to `docs/assets/` at 1280×800 or higher.

---

## Required screenshots

### 1. Tests passing — `docs/assets/tests_passed.png`

```bash
uv run pytest tests/ -v
```

Capture the full terminal output showing:
- All 73 test names with `PASSED`
- Final line: `73 passed in X.XXs`

---

### 2. Swagger UI — `docs/assets/swagger.png`

Start the API:
```bash
uv run uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` in a browser.

Capture:
- The full Swagger UI page
- All three endpoints visible: `/health`, `/report`, `/history`
- Expand `/report` to show the query parameters

---

### 3. /health response — `docs/assets/api_health.png`

In Swagger or browser:
```
GET http://localhost:8000/health
```

Capture the JSON response:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "mock_mode": true,
  "llm_enabled": false
}
```

---

### 4. /report BTCUSDT response — `docs/assets/api_report.png`

```
GET http://localhost:8000/report?symbol=BTCUSDT
```

Capture the full JSON response showing:
- `market_bias`, `confidence_score`
- `key_signals` list
- `risk_warnings`
- `narrative`
- `market_structure` block (bias, RSI, BOS/CHOCH, order_blocks)
- `price_source`, `news_source`, `analysis_engine`

Use a JSON formatter / browser dev tools / Swagger for clean rendering.

---

### 5. /history response — `docs/assets/api_history.png`

First generate 2–3 reports by calling `/report` a few times, then:
```
GET http://localhost:8000/history?symbol=BTCUSDT&limit=5
```

Capture the list of reports showing newest-first ordering and all provenance fields.

---

### 6. Telegram /report — `docs/assets/telegram_report.png`

*Requires `TELEGRAM_BOT_TOKEN` in `.env`.*

Start the bot:
```bash
uv run python -m telegram_bot.main
```

Send in Telegram:
```
/report BTCUSDT
```

Capture the formatted bot reply showing:
- Bias with emoji (🟢/🔴/🟡)
- Market structure section (RSI, MA, BOS event)
- Key signals list
- Risk warnings
- Narrative
- Footer: `Engine: rule-based | Price: mock | News: mock`

---

### 7. README Mermaid diagram — `docs/assets/readme_diagram.png`

Open `README.md` on GitHub (after pushing) and take a screenshot of the rendered Mermaid architecture diagram.

---

## Optional screenshots

| Screenshot | Path | Notes |
|---|---|---|
| API with live Binance data | `docs/assets/api_report_live.png` | `MOCK_MODE=false`, shows `price_source: binance` |
| CoinGecko fallback | `docs/assets/api_report_coingecko.png` | With Binance blocked, shows `price_source: coingecko` |
| /report ETHUSDT | `docs/assets/api_report_eth.png` | Shows multi-symbol support |
| pytest coverage report | `docs/assets/coverage.png` | Run `uv run pytest --cov` after adding coverage dep |

---

## Capture tips

- Use **Firefox / Chrome full-page screenshot** (F12 → Screenshot) for JSON responses — avoids scrolling cuts
- For Swagger: expand the endpoint, click "Try it out", execute, then capture the response panel
- For Telegram: use Telegram Desktop on PC for a clean capture without phone UI elements
- Dark mode looks better in portfolio screenshots — enable in browser and Telegram if available
