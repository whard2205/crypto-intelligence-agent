# Portfolio Copy

Ready-to-use text for GitHub, CV, LinkedIn, and portfolio.

---

## Short description (1–2 sentences)

AI-powered crypto market intelligence system built with LangGraph multi-agent pipelines, FastAPI, and a Telegram bot. Generates structured `IntelligenceReport` objects using ICT/Smart Money Concepts analysis, with a three-tier fallback data stack (Binance → CoinGecko → Mock) and full data provenance on every report — zero cost in development mode.

---

## Medium description (paragraph)

A production-structured crypto market intelligence system that demonstrates multi-agent AI architecture using LangGraph. The system runs a parallel fan-out pipeline of four collector agents and three independent analyzer agents (sentiment, ICT/SMC market structure, risk), merging results through a deterministic supervisor that applies vote-based market bias with strict risk consistency guarantees. The FastAPI layer exposes `/report`, `/history`, and `/health` endpoints with optional API key auth; a Telegram bot delivers HTML-formatted reports on demand. Data sources use a three-tier fallback chain (Binance public REST → CoinGecko public REST → Mock) with full provenance metadata (`price_source`, `news_source`, `analysis_engine`) on every report. The system is designed mock-first: `MOCK_MODE=true` runs the full pipeline without any external API calls, making it safe for CI/CD and demo environments. 73 automated tests, 0 paid APIs required.

---

## CV bullet points

**Choose 2–4 depending on available space:**

- Built an AI-powered crypto market intelligence system using **LangGraph** multi-agent pipelines with parallel fan-out collectors and analyzers, a **FastAPI** REST API, and a **Telegram bot**, producing structured `IntelligenceReport` objects with ICT/Smart Money Concepts market structure analysis.

- Designed a mock-first multi-tier data adapter pattern (Binance → CoinGecko → Mock) with `FallbackAdapter` chaining and per-report provenance metadata, enabling zero-cost CI/CD and seamless live-data switching without code changes.

- Implemented a deterministic rule-based supervisor with vote-based market bias, strict risk consistency invariants (RSI overbought warnings always reflected in narrative), and 73 automated unit + integration tests using pytest + respx.

- Delivered a SQLite-backed report history service with async I/O (aiosqlite), auto-pruning to 100 rows per symbol, and a `/history` REST endpoint with symbol validation and limit capping.

---

## LinkedIn post draft

Just shipped a personal project I'm genuinely proud of: **Crypto Market Intelligence Agent** — an AI-powered multi-agent system built with LangGraph, FastAPI, and a Telegram bot.

Here's what it does:

- Runs a **parallel LangGraph pipeline**: 4 collectors → 3 independent analyzers (sentiment, ICT/SMC market structure, risk) → deterministic supervisor
- **ICT/Smart Money Concepts** analysis: swing high/low detection, liquidity sweeps, order blocks, BOS/CHOCH classification, RSI/MACD/momentum confluence
- **Three-tier data stack**: Binance REST → CoinGecko REST → Mock, with automatic fallback and full provenance metadata (`price_source`, `news_source`, `analysis_engine`) on every report
- **Zero-cost development mode**: `MOCK_MODE=true` runs the entire pipeline offline — no API keys, no network, safe for CI/CD
- **FastAPI** REST API with `/report`, `/history`, `/health` endpoints + optional API key auth
- **Telegram bot** with `/report BTCUSDT` command and HTML-formatted structured output
- **SQLite report history** with async I/O and auto-pruning
- **73 automated tests** — unit + integration, all running offline

The architecture is intentionally extensible: Claude AI analysis, a scheduler for periodic reports, XGBoost ML predictions, and Reddit/Etherscan adapters are all planned as future phases — but the core pipeline is production-structured today.

Tech: Python 3.12 · LangGraph · FastAPI · python-telegram-bot · httpx · aiosqlite · feedparser · pydantic-settings · uv · pytest

GitHub: [link]

#Python #AI #LangGraph #FastAPI #MultiAgent #CryptoIntelligence #SoftwareEngineering

---

## Tech stack summary (for portfolio cards / skills sections)

| Category | Technologies |
|---|---|
| Pipeline orchestration | LangGraph (StateGraph, parallel fan-out, conditional routing) |
| REST API | FastAPI, Uvicorn, Pydantic v2 |
| Telegram bot | python-telegram-bot v20 (async) |
| HTTP client | httpx (async) |
| News parsing | feedparser |
| Configuration | pydantic-settings |
| Database | SQLite + aiosqlite (async) |
| Testing | pytest, pytest-asyncio, respx |
| Packaging | uv, hatchling |
| Language | Python 3.12 |
| Data sources | Binance public REST, CoinGecko public REST, RSS feeds (CoinTelegraph, CoinDesk, Decrypt) |
| Analysis | ICT/SMC (swing detection, liquidity sweeps, order blocks, BOS/CHOCH), RSI, MACD, momentum |

---

## Recruiter talking points

**What is it?**
An AI-powered crypto market intelligence system — not a trading bot. It generates structured analysis reports (market bias, confidence score, key signals, risk warnings, narrative) using a multi-agent LangGraph pipeline. Think of it as a research analyst that runs 24/7 and delivers structured intel on demand.

**Why LangGraph instead of a simple script?**
The analysis naturally decomposes into independent parallel agents: price collection, news collection, on-chain data, social data, sentiment analysis, market structure analysis, and risk analysis. LangGraph's StateGraph handles the fan-out/fan-in pattern cleanly, with proper state management and conditional routing when data is unavailable. This also makes each analyzer independently testable and replaceable.

**What's the ICT/SMC analysis?**
ICT (Inner Circle Trader) / Smart Money Concepts is a well-known trading methodology based on institutional order flow. The system detects swing highs/lows, identifies where "smart money" swept liquidity, marks order blocks (institutional entry zones), and classifies BOS (Break of Structure) vs CHOCH (Change of Character) events. This adds domain-specific depth beyond simple RSI/MACD signals.

**How does the fallback adapter work?**
The `FallbackAdapter` chains multiple data sources: if Binance is unavailable, it transparently falls back to CoinGecko, and in development to mock data. Every report carries `price_source` and `news_source` fields so you always know which data was actually used. In production mode, the mock fallback is deliberately excluded — failures surface as data gaps rather than silently returning fake data.

**Why mock-first?**
The full pipeline runs deterministically without any network calls when `MOCK_MODE=true`. This means tests are fast, reproducible, and work in any CI/CD environment. It also means a recruiter can clone the repo and run the full demo in under a minute without API keys.

**What's next?**
Claude AI integration (LLM_ENABLED=true) is planned as Phase 9 — the supervisor node has an async branch ready for it, gated by settings. Other planned phases: APScheduler for periodic reports, Reddit sentiment adapter, Etherscan on-chain data, XGBoost ML model for directional probability, and Monte Carlo confidence intervals.

**How does this demonstrate production readiness?**
- Structured error handling at every layer (data gaps propagate gracefully, not as exceptions)
- Dependency injection via factory pattern (adapters injected into graph nodes, not hardcoded)
- Pydantic v2 config and response schemas with validation
- Optional API authentication middleware
- Async throughout (FastAPI, aiosqlite, httpx, python-telegram-bot v20)
- 73 automated tests with no external dependencies in test mode
