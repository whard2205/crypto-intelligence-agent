# Phase 9 — HMM Regime Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stateless GaussianHMM regime detector that classifies the current market as `bull_trending`, `ranging`, or `bear_trending`, surfaces it as "Market Regime Context" in the intelligence report's `key_signals`, and provides a +0.05 confidence boost when the regime aligns with the overall bias.

**Architecture:** A new pure function `detect_hmm_regime(ohlcv)` in `graph/hmm_regime.py` is called from `make_market_structure_analyzer(settings)` (factory-refactored from the current plain function) when `ML_ENABLED=True`. The result lives in `market_structure_analysis["market_regime"]` (dict or None), flows through `merge_analysis` unchanged into `analysis["market_structure"]`, and is read by `_deterministic_supervisor` to inject a key signal and an optional confidence boost.

**Tech Stack:** `hmmlearn>=0.3` (GaussianHMM), `numpy` (pulled in by hmmlearn), `pytest` with `asyncio_mode="auto"`, `unittest.mock.patch`.

**Spec:** `docs/superpowers/specs/2026-05-06-hmm-regime-detection-design.md`

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `graph/hmm_regime.py` | `detect_hmm_regime(ohlcv, n_states=3) -> dict \| None` |
| `tests/unit/test_hmm_regime.py` | 6 unit tests for the HMM detector |

### Modified files
| File | Change |
|---|---|
| `pyproject.toml` | Add `hmmlearn>=0.3` to `dependencies` |
| `agents/analyzers/market_structure_analyzer.py` | Wrap existing function in factory `make_market_structure_analyzer(settings)`; call `detect_hmm_regime` when `ML_ENABLED=True`; add `market_regime` field to output |
| `graph/pipeline.py` | Use `make_market_structure_analyzer(settings)` instead of bare `analyze_market_structure` |
| `agents/supervisor.py` | Extract `regime` from `ms["market_regime"]`; append `"Market Regime Context: {regime}"` to `key_signals`; boost `confidence` by 0.05 when aligned |
| `tests/unit/test_analyzers.py` | Update 3 existing market-structure tests to use factory; add 3 new ML gate tests |
| `tests/unit/test_supervisor.py` | Add 3 tests for regime injection |

---

## Task 1: Add `hmmlearn` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `hmmlearn` to `pyproject.toml`**

In `pyproject.toml`, add `hmmlearn>=0.3` to the `dependencies` list (after `feedparser`):

```toml
[project]
name = "crypto-intelligence-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langgraph>=0.2",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "anthropic>=0.34",
    "httpx>=0.27",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "aiosqlite>=0.20",
    "apscheduler>=3.10,<4",
    "feedparser>=6.0",
    "python-telegram-bot>=20.8",
    "hmmlearn>=0.3",
]
```

- [ ] **Step 2: Install the dependency**

```
uv sync
```

Expected: `hmmlearn` and `numpy` installed without errors.

- [ ] **Step 3: Verify import works**

```
uv run python -c "from hmmlearn.hmm import GaussianHMM; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```
git add pyproject.toml uv.lock
git commit -m "chore: add hmmlearn dependency for HMM regime detection"
```

---

## Task 2: `detect_hmm_regime` function

**Files:**
- Create: `graph/hmm_regime.py`
- Create: `tests/unit/test_hmm_regime.py`

- [ ] **Step 1: Create `tests/unit/test_hmm_regime.py` with all 6 tests**

```python
import math
import sys
from unittest.mock import patch

import pytest

from tests.conftest import make_ohlcv


def _make_uptrend_ohlcv(n: int = 60) -> list[dict]:
    """60 candles with a strong, consistent uptrend — all log returns positive."""
    candles = []
    base = 100.0
    for i in range(n):
        close = base * (1.005 ** i)
        open_ = close * 0.999
        candles.append({
            "open": round(open_, 4), "high": round(close * 1.002, 4),
            "low": round(open_ * 0.998, 4), "close": round(close, 4),
            "volume": 10000,
        })
    return candles


def test_valid_input_returns_regime_dict():
    from graph.hmm_regime import detect_hmm_regime
    result = detect_hmm_regime(make_ohlcv(60))
    assert result is not None
    assert result["regime"] in {"bull_trending", "ranging", "bear_trending"}
    assert result["n_states"] == 3
    assert result["source"] == "hmm"


def test_short_input_returns_none():
    from graph.hmm_regime import detect_hmm_regime
    result = detect_hmm_regime(make_ohlcv(29))
    assert result is None


def test_import_error_returns_none():
    from graph.hmm_regime import detect_hmm_regime
    blocked = {"hmmlearn": None, "hmmlearn.hmm": None}
    with patch.dict(sys.modules, blocked):
        result = detect_hmm_regime(make_ohlcv(60))
    assert result is None


def test_uptrend_data_regime_is_bull_trending():
    from graph.hmm_regime import detect_hmm_regime
    result = detect_hmm_regime(_make_uptrend_ohlcv(60))
    assert result is not None
    assert result["regime"] == "bull_trending"


def test_does_not_mutate_input():
    from graph.hmm_regime import detect_hmm_regime
    ohlcv = make_ohlcv(60)
    original = [dict(c) for c in ohlcv]
    detect_hmm_regime(ohlcv)
    assert ohlcv == original


def test_deterministic_with_random_state():
    from graph.hmm_regime import detect_hmm_regime
    ohlcv = make_ohlcv(60)
    result1 = detect_hmm_regime(ohlcv)
    result2 = detect_hmm_regime(ohlcv)
    assert result1 == result2
```

- [ ] **Step 2: Run to confirm all 6 tests fail**

```
uv run pytest tests/unit/test_hmm_regime.py -v
```

Expected: all 6 FAIL — `ModuleNotFoundError: No module named 'graph.hmm_regime'`

- [ ] **Step 3: Create `graph/hmm_regime.py`**

```python
from __future__ import annotations
import logging
import math

logger = logging.getLogger(__name__)

_REGIME_LABELS = ("bear_trending", "ranging", "bull_trending")


def detect_hmm_regime(ohlcv: list[dict], n_states: int = 3) -> dict | None:
    if len(ohlcv) < 30:
        logger.warning(
            "HMM regime detection requires >= 30 candles, got %d", len(ohlcv)
        )
        return None

    try:
        from hmmlearn.hmm import GaussianHMM
        import numpy as np
    except ImportError:
        logger.warning("hmmlearn not installed — market regime detection disabled")
        return None

    try:
        closes = [float(c["close"]) for c in ohlcv]
        log_returns = [
            math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
        ]

        volatility: list[float] = []
        for i in range(len(log_returns)):
            window = log_returns[max(0, i - 4): i + 1]
            mean_w = sum(window) / len(window)
            var_w = sum((x - mean_w) ** 2 for x in window) / len(window)
            volatility.append(math.sqrt(var_w))

        X = np.array([[r, v] for r, v in zip(log_returns, volatility)])

        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=100,
            random_state=42,
        )
        model.fit(X)
        states = model.predict(X)

        state_sums: dict[int, list[float]] = {i: [] for i in range(n_states)}
        for state, ret in zip(states.tolist(), log_returns):
            state_sums[int(state)].append(ret)

        state_means = {
            s: (sum(vs) / len(vs) if vs else 0.0)
            for s, vs in state_sums.items()
        }

        sorted_states = sorted(state_means, key=lambda s: state_means[s])
        label_map = {
            state: _REGIME_LABELS[rank]
            for rank, state in enumerate(sorted_states)
        }

        return {
            "regime":   label_map[int(states[-1])],
            "n_states": n_states,
            "source":   "hmm",
        }

    except Exception as exc:
        logger.warning("HMM regime detection failed: %s", exc)
        return None
```

- [ ] **Step 4: Run tests to confirm all 6 pass**

```
uv run pytest tests/unit/test_hmm_regime.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```
git add graph/hmm_regime.py tests/unit/test_hmm_regime.py
git commit -m "feat: add detect_hmm_regime for market regime context"
```

---

## Task 3: Refactor analyzer → factory + ML gate

**Files:**
- Modify: `agents/analyzers/market_structure_analyzer.py`
- Modify: `graph/pipeline.py`
- Modify: `tests/unit/test_analyzers.py`

The existing `analyze_market_structure` plain function becomes an inner function returned by `make_market_structure_analyzer(settings)`. The 3 existing market-structure tests import the bare function — they break after refactoring. Write the updated tests first.

- [ ] **Step 1: Update `tests/unit/test_analyzers.py` — market structure section**

Replace the three existing market-structure tests (the block starting with `# --- Market structure ---`) with the following 6 tests (3 updated + 3 new):

```python
# --- Market structure ---

async def test_market_structure_returns_expected_fields():
    from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
    node = make_market_structure_analyzer(Settings(LLM_ENABLED=False, ML_ENABLED=False))
    state = _state_with_context()
    result = await node(state)
    ms = result["market_structure_analysis"]

    assert ms["bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= ms["rsi"] <= 100.0
    assert ms["ma_trend"] in ("uptrend", "downtrend", "sideways")
    assert 0.0 <= ms["confidence_score"] <= 1.0
    assert isinstance(ms["explanation"], str)
    assert isinstance(ms["swing_highs"], list)
    assert isinstance(ms["swing_lows"], list)
    assert isinstance(ms["bos_choch"], list)
    assert ms["ml_probability_1r"] is None
    assert ms["market_regime"] is None  # ML_ENABLED=False


async def test_market_structure_insufficient_data_returns_neutral():
    from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
    node = make_market_structure_analyzer(Settings(LLM_ENABLED=False, ML_ENABLED=False))
    state = _state_with_context(ohlcv=[])
    result = await node(state)
    ms = result["market_structure_analysis"]
    assert ms["bias"] == "neutral"
    assert ms["confidence_score"] == 0.0
    assert ms["swing_highs"] == []
    assert ms["bos_choch"] == []


async def test_market_structure_rsi_in_valid_range():
    from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
    node = make_market_structure_analyzer(Settings(LLM_ENABLED=False, ML_ENABLED=False))
    state = _state_with_context(ohlcv=make_ohlcv(50))
    result = await node(state)
    rsi = result["market_structure_analysis"]["rsi"]
    assert 0.0 <= rsi <= 100.0


async def test_market_structure_ml_enabled_calls_hmm():
    from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
    from unittest.mock import patch
    settings = Settings(LLM_ENABLED=False, ML_ENABLED=True)
    node = make_market_structure_analyzer(settings)
    mock_result = {"regime": "bull_trending", "n_states": 3, "source": "hmm"}
    with patch(
        "agents.analyzers.market_structure_analyzer.detect_hmm_regime",
        return_value=mock_result,
    ) as mock_hmm:
        state = _state_with_context(ohlcv=make_ohlcv(60))
        result = await node(state)
    assert result["market_structure_analysis"]["market_regime"] == mock_result
    mock_hmm.assert_called_once()


async def test_market_structure_ml_disabled_market_regime_is_none():
    from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
    node = make_market_structure_analyzer(Settings(LLM_ENABLED=False, ML_ENABLED=False))
    state = _state_with_context(ohlcv=make_ohlcv(60))
    result = await node(state)
    assert result["market_structure_analysis"]["market_regime"] is None


async def test_market_structure_hmm_failure_market_regime_is_none():
    from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
    from unittest.mock import patch
    settings = Settings(LLM_ENABLED=False, ML_ENABLED=True)
    node = make_market_structure_analyzer(settings)
    with patch(
        "agents.analyzers.market_structure_analyzer.detect_hmm_regime",
        side_effect=RuntimeError("fail"),
    ):
        state = _state_with_context(ohlcv=make_ohlcv(60))
        result = await node(state)
    assert result["market_structure_analysis"]["market_regime"] is None
```

- [ ] **Step 2: Run to confirm failures**

```
uv run pytest tests/unit/test_analyzers.py -v --tb=short
```

Expected: 3 updated tests FAIL (ImportError on `make_market_structure_analyzer`), 3 new tests FAIL (same).

- [ ] **Step 3: Refactor `agents/analyzers/market_structure_analyzer.py`**

Add the import at the top of the file (after `from graph.state import AgentState`):

```python
from config.settings import Settings
from graph.hmm_regime import detect_hmm_regime
```

Replace the module-level `async def analyze_market_structure(state: AgentState) -> dict:` with a factory. The full replacement — only the outer wrapper and the parts that change inside:

```python
def make_market_structure_analyzer(settings: Settings):
    async def analyze_market_structure(state: AgentState) -> dict:
        context = state.get("context") or {}
        ohlcv   = context.get("price_summary", {}).get("ohlcv_24h", [])

        _empty = {
            "bias": "neutral",
            "swing_highs": [], "swing_lows": [],
            "liquidity_sweeps": [], "order_blocks": [], "bos_choch": [],
            "volume_confirmed": False, "invalidation_level": None,
            "rsi": 50.0, "macd_histogram_slope": 0.0,
            "ma_trend": "sideways", "momentum_pct": 0.0,
            "confidence_score": 0.0,
            "explanation": "Insufficient OHLCV data for market structure analysis.",
            "market_regime":     None,
            "ml_probability_1r": None, "ml_probability_2r": None,
        }

        if not ohlcv or len(ohlcv) < 10:
            return {"market_structure_analysis": _empty}

        highs   = [float(c["high"])          for c in ohlcv]
        lows    = [float(c["low"])           for c in ohlcv]
        closes  = [float(c["close"])         for c in ohlcv]
        volumes = [float(c.get("volume", 0)) for c in ohlcv]

        swing_highs  = _detect_swing_highs(highs, n=3)
        swing_lows   = _detect_swing_lows(lows, n=3)
        sweeps       = _detect_liquidity_sweeps(highs, lows, closes, swing_highs, swing_lows)
        bos_choch    = _deduplicate_bos(_detect_bos_choch(closes, swing_highs, swing_lows))
        order_blocks = _detect_order_blocks(highs, lows, closes, bos_choch)
        vol_confirmed = _volume_confirmed(volumes)
        vol_missing   = _volumes_all_zero(volumes)
        invalidation  = _invalidation_level(bos_choch, swing_highs, swing_lows)

        bias = "neutral"
        if bos_choch:
            bias = bos_choch[-1]["direction"]

        rsi        = _compute_rsi(closes)
        macd_slope = _compute_macd_histogram_slope(closes)
        ma20       = _sma(closes, 20)
        ma50       = _sma(closes, 50)
        ma_trend   = _ma_trend(closes[-1], ma20, ma50)
        momentum   = round((closes[-1] - closes[-5]) / closes[-5] * 100, 2) if len(closes) >= 5 else 0.0

        confidence, explanation = _score_and_explain(
            bias, bos_choch, sweeps, order_blocks, vol_confirmed,
            rsi, macd_slope, ma_trend, momentum,
            vol_data_missing=vol_missing,
        )

        market_regime = None
        if settings.ML_ENABLED:
            try:
                market_regime = detect_hmm_regime(ohlcv)
            except Exception as exc:
                logger.warning("HMM regime detection failed unexpectedly: %s", exc)

        return {
            "market_structure_analysis": {
                "bias":                  bias,
                "swing_highs":           swing_highs,
                "swing_lows":            swing_lows,
                "liquidity_sweeps":      sweeps,
                "order_blocks":          order_blocks,
                "bos_choch":             bos_choch,
                "volume_confirmed":      vol_confirmed,
                "invalidation_level":    invalidation,
                "rsi":                   round(rsi, 1),
                "macd_histogram_slope":  round(macd_slope, 6),
                "ma_trend":              ma_trend,
                "momentum_pct":          momentum,
                "confidence_score":      round(confidence, 2),
                "explanation":           explanation,
                "market_regime":         market_regime,
                "ml_probability_1r":     None,
                "ml_probability_2r":     None,
            }
        }
    return analyze_market_structure
```

All private helper functions (`_detect_swing_highs`, `_detect_swing_lows`, etc.) remain unchanged below the factory.

- [ ] **Step 4: Update `graph/pipeline.py`**

Change the import inside `build_graph`:

```python
# Before
from agents.analyzers.market_structure_analyzer import analyze_market_structure

# After
from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
```

Change the node registration:

```python
# Before
workflow.add_node("analyze_market_structure", analyze_market_structure)

# After
workflow.add_node("analyze_market_structure", make_market_structure_analyzer(settings))
```

- [ ] **Step 5: Run tests to confirm all 6 pass**

```
uv run pytest tests/unit/test_analyzers.py -v --tb=short
```

Expected: 6 PASSED

- [ ] **Step 6: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 7: Commit**

```
git add agents/analyzers/market_structure_analyzer.py graph/pipeline.py tests/unit/test_analyzers.py
git commit -m "feat: refactor market structure analyzer to factory, add ML_ENABLED HMM gate"
```

---

## Task 4: Supervisor regime injection

**Files:**
- Modify: `agents/supervisor.py`
- Modify: `tests/unit/test_supervisor.py`

The supervisor's `_deterministic_supervisor` reads `market_regime` from `ms` (which is `analysis["market_structure"]`), boosts confidence when aligned, and appends a `"Market Regime Context: {regime}"` key signal.

- [ ] **Step 1: Add 3 failing tests to `tests/unit/test_supervisor.py`**

Append after the last existing test in the file:

```python
# ---------------------------------------------------------------------------
# Market regime context injection
# ---------------------------------------------------------------------------

def _ms_with_regime(regime: str | None) -> dict:
    base = {
        "bias": "bullish", "rsi": 58.0, "ma_trend": "uptrend",
        "confidence_score": 0.65, "explanation": "BOS bullish",
        "swing_highs": [65100.0], "swing_lows": [63900.0],
        "liquidity_sweeps": [], "order_blocks": [],
        "bos_choch": [{"type": "BOS", "direction": "bullish",
                       "break_level": 65100.0, "candle_idx": 25}],
        "volume_confirmed": True, "invalidation_level": 63900.0,
        "macd_histogram_slope": 0.002, "momentum_pct": 1.2,
        "ml_probability_1r": None, "ml_probability_2r": None,
        "market_regime": None,
    }
    if regime is not None:
        base["market_regime"] = {"regime": regime, "n_states": 3, "source": "hmm"}
    return base


async def test_supervisor_aligned_regime_adds_signal_and_boosts_confidence():
    node = make_supervisor(Settings(LLM_ENABLED=False))

    state_no = _state_with_full_analysis()
    state_aligned = _state_with_full_analysis(
        market_structure=_ms_with_regime("bull_trending")
    )

    result_no      = await node(state_no)
    result_aligned = await node(state_aligned)

    signals = result_aligned["report"]["key_signals"]
    assert any("Market Regime Context: bull_trending" in s for s in signals)
    assert result_aligned["report"]["confidence_score"] >= result_no["report"]["confidence_score"]


async def test_supervisor_misaligned_regime_adds_signal_no_boost():
    node = make_supervisor(Settings(LLM_ENABLED=False))

    # bias=bullish (from default_ms) but regime=ranging → misaligned
    state_no       = _state_with_full_analysis()
    state_mismatch = _state_with_full_analysis(
        market_structure=_ms_with_regime("ranging")
    )

    result_no       = await node(state_no)
    result_mismatch = await node(state_mismatch)

    signals = result_mismatch["report"]["key_signals"]
    assert any("Market Regime Context: ranging" in s for s in signals)
    assert result_mismatch["report"]["confidence_score"] == result_no["report"]["confidence_score"]


async def test_supervisor_none_regime_no_injection():
    node = make_supervisor(Settings(LLM_ENABLED=False))
    state = _state_with_full_analysis()  # market_regime absent from default_ms
    result = await node(state)
    assert not any("Market Regime Context" in s for s in result["report"]["key_signals"])
```

- [ ] **Step 2: Run to confirm all 3 tests fail**

```
uv run pytest tests/unit/test_supervisor.py -v -k "regime" --tb=short
```

Expected: 3 FAIL — `AssertionError` (no regime signal in key_signals yet)

- [ ] **Step 3: Update `agents/supervisor.py`**

In `_deterministic_supervisor`, make three targeted insertions:

**Insertion A — right after `ms = analysis.get("market_structure") or {}` (line 25):**

```python
    ms              = analysis.get("market_structure") or {}
    # --- NEW ---
    regime_data = ms.get("market_regime")
    regime = regime_data.get("regime") if regime_data else None
    # -----------
```

**Insertion B — right after `confidence = round(max(0.10, min(1.0, base_conf - gap_penalty)), 2)` (line 81):**

```python
    confidence  = round(max(0.10, min(1.0, base_conf - gap_penalty)), 2)
    # --- NEW ---
    _REGIME_BIAS = {
        "bullish": "bull_trending",
        "bearish": "bear_trending",
        "neutral": "ranging",
    }
    if regime and _REGIME_BIAS.get(market_bias) == regime:
        confidence = round(min(1.0, confidence + 0.05), 2)
    # -----------
```

**Insertion C — right after `if ma_trend in ("uptrend", "downtrend"):` block (after the `key_signals.append(f"MA trend: {ma_trend}")` line) and before `key_signals.append(f"RSI: {rsi:.0f}")`:**

```python
    if ma_trend in ("uptrend", "downtrend"):
        key_signals.append(f"MA trend: {ma_trend}")
    # --- NEW ---
    if regime:
        key_signals.append(f"Market Regime Context: {regime}")
    # -----------
    key_signals.append(f"RSI: {rsi:.0f}")
```

- [ ] **Step 4: Run tests to confirm all 3 pass**

```
uv run pytest tests/unit/test_supervisor.py -v -k "regime" --tb=short
```

Expected: 3 PASSED

- [ ] **Step 5: Run full unit suite for regressions**

```
uv run pytest tests/unit/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```
git add agents/supervisor.py tests/unit/test_supervisor.py
git commit -m "feat: inject market regime context into supervisor key_signals and confidence"
```

---

## Task 5: Full integration smoke test

**Files:** no changes — validation only

- [ ] **Step 1: Run the full test suite**

```
uv run pytest tests/ -v --tb=short
```

Expected: all PASSED

- [ ] **Step 2: Smoke-test the pipeline end-to-end with ML_ENABLED=True**

```
uv run python -c "
import asyncio
from config.settings import Settings
from graph.pipeline import build_graph
from data_sources.factory import build_adapters

settings = Settings(ENV='test', MOCK_MODE=True, ML_ENABLED=True)
adapters = build_adapters(settings)
graph = build_graph(settings, **adapters)

async def run():
    import uuid
    from datetime import datetime, timezone
    state = {
        'run_id': str(uuid.uuid4()),
        'symbol': 'BTCUSDT',
        'requested_at': datetime.now(timezone.utc).isoformat(),
        'price_data': None, 'news_data': [], 'onchain_data': None,
        'social_data': None, 'funding_rate_data': None,
        'context': None, 'sentiment_analysis': None,
        'market_structure_analysis': None, 'risk_analysis': None,
        'analysis': None, 'report': None, 'data_gaps': [], 'errors': [],
    }
    result = await graph.ainvoke(state)
    report = result['report']
    print('bias:', report['market_bias'])
    print('confidence:', report['confidence_score'])
    print('key_signals:', report['key_signals'])
    regime_signal = [s for s in report['key_signals'] if 'Market Regime Context' in s]
    print('regime signal:', regime_signal)

asyncio.run(run())
"
```

Expected: Output includes a `Market Regime Context: ...` entry in `key_signals`.

- [ ] **Step 3: Verify ML_ENABLED=False leaves pipeline unchanged**

```
uv run python -c "
import asyncio
from config.settings import Settings
from graph.pipeline import build_graph
from data_sources.factory import build_adapters

settings = Settings(ENV='test', MOCK_MODE=True, ML_ENABLED=False)
adapters = build_adapters(settings)
graph = build_graph(settings, **adapters)

async def run():
    import uuid
    from datetime import datetime, timezone
    state = {
        'run_id': str(uuid.uuid4()), 'symbol': 'BTCUSDT',
        'requested_at': datetime.now(timezone.utc).isoformat(),
        'price_data': None, 'news_data': [], 'onchain_data': None,
        'social_data': None, 'funding_rate_data': None,
        'context': None, 'sentiment_analysis': None,
        'market_structure_analysis': None, 'risk_analysis': None,
        'analysis': None, 'report': None, 'data_gaps': [], 'errors': [],
    }
    result = await graph.ainvoke(state)
    report = result['report']
    regime_signal = [s for s in report['key_signals'] if 'Market Regime Context' in s]
    assert regime_signal == [], f'Expected no regime signal, got: {regime_signal}'
    print('ML_ENABLED=False: no regime signal — OK')

asyncio.run(run())
"
```

Expected: `ML_ENABLED=False: no regime signal — OK`
