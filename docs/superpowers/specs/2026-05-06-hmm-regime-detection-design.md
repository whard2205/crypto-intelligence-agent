# Phase 9 — HMM Regime Detection (Market Regime Context)

**Date:** 2026-05-06
**Status:** Approved, pending implementation

---

## Overview

Add Hidden Markov Model (HMM) regime detection to the market structure analyzer. The model classifies the current market into one of three regimes — `bull_trending`, `ranging`, `bear_trending` — based on OHLCV price data. The result is surfaced as **Market Regime Context** in the final intelligence report: a filter/penjelas kondisi market, bukan entry signal.

Gated by the existing `ML_ENABLED` setting. When disabled, pipeline is unchanged.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Number of states | 3 (`bull_trending` / `ranging` / `bear_trending`) | Aligns with existing `market_bias` taxonomy; stable with 60 candles |
| Framing | "Market Regime Context" | Filter/context, not entry signal |
| Integration point | Inside `analyze_market_structure` (factory pattern) | No `AgentState` changes; HMM logic isolated in separate module |
| Field name | `market_regime` (dict) in `market_structure_analysis` | Consistent across all files; supervisor reads dict |
| Confidence effect | +0.05 when regime aligns with bias | Regime confirms analysis, doesn't drive it |
| Fallback | `market_regime: None`, log warning, pipeline continues | HMM is optional; server must not crash on ML failure |

---

## Files

### New files

| File | Purpose |
|---|---|
| `graph/hmm_regime.py` | `detect_hmm_regime(ohlcv, n_states=3) -> dict \| None` |
| `tests/unit/test_hmm_regime.py` | ~6 unit tests for HMM detector |

### Modified files

| File | Change |
|---|---|
| `agents/analyzers/market_structure_analyzer.py` | Refactor to factory `make_market_structure_analyzer(settings)`; call `detect_hmm_regime` when `ML_ENABLED=True` |
| `graph/pipeline.py` | Use `make_market_structure_analyzer(settings)` instead of plain function |
| `agents/supervisor.py` | Read `market_regime` dict from `market_structure_analysis`; inject into `key_signals` + confidence |
| `tests/unit/test_market_structure_analyzer.py` | Add tests for factory + `ML_ENABLED` gate |
| `tests/unit/test_supervisor.py` | Add tests for `market_regime` injection |
| `pyproject.toml` | Add `hmmlearn` dependency |

---

## `detect_hmm_regime` Specification

### Signature

```python
# graph/hmm_regime.py
def detect_hmm_regime(ohlcv: list[dict], n_states: int = 3) -> dict | None:
    ...
```

### Input

- `ohlcv`: list of candle dicts with `"close"` key, minimum 30 candles
- `n_states`: number of hidden states (default 3)

### Features (2 per candle)

- **Log return**: `ln(close[i] / close[i-1])`
- **Rolling volatility**: std of last 5 log returns

### Model

```python
GaussianHMM(
    n_components=3,
    covariance_type="diag",
    n_iter=100,
    random_state=42,
)
```

### State Label Mapping

Sorted by mean log return across all candles assigned to each state:

| Mean return rank | Label |
|---|---|
| Highest | `bull_trending` |
| Middle | `ranging` |
| Lowest | `bear_trending` |

### Output

```python
{
    "regime":   "bull_trending",  # current regime (last candle)
    "n_states": 3,
    "source":   "hmm",
}
```

### Fallback

Returns `None` (with `logger.warning`) in any of these cases:
- `len(ohlcv) < 30`
- `hmmlearn` not installed (`ImportError`)
- HMM fit raises any exception

---

## Factory Pattern

```python
# agents/analyzers/market_structure_analyzer.py

def make_market_structure_analyzer(settings: Settings):
    async def analyze_market_structure(state: AgentState) -> dict:
        # ... existing logic unchanged ...

        market_regime = None
        if settings.ML_ENABLED:
            market_regime = detect_hmm_regime(ohlcv)

        return {
            "market_structure_analysis": {
                # ... existing fields ...
                "market_regime":      market_regime,   # dict | None
                "ml_probability_1r":  None,
                "ml_probability_2r":  None,
            }
        }
    return analyze_market_structure
```

### `pipeline.py` change

```python
# before
workflow.add_node("analyze_market_structure", analyze_market_structure)

# after
workflow.add_node("analyze_market_structure", make_market_structure_analyzer(settings))
```

---

## Supervisor Integration

### Reading the dict

Supervisor already has `ms = analysis.get("market_structure") or {}` — regime is read from there:

```python
regime_data = ms.get("market_regime")   # dict | None
regime = regime_data.get("regime") if regime_data else None
```

### `key_signals` injection

If `regime` is not None, append to `key_signals`:
```
"Market Regime Context: bull_trending"
```

### Confidence boost

```python
REGIME_BIAS_ALIGNMENT = {
    "bullish":  "bull_trending",
    "bearish":  "bear_trending",
    "neutral":  "ranging",
}

if regime and REGIME_BIAS_ALIGNMENT.get(bias) == regime:
    confidence_score = min(1.0, confidence_score + 0.05)
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `ML_ENABLED=False` | `market_regime: None`; `detect_hmm_regime` not called |
| `hmmlearn` not installed | `ImportError` caught; log warning; `market_regime: None` |
| OHLCV < 30 candles | Return `None`; log warning |
| HMM fit fails | Exception caught; log warning; `market_regime: None` |
| `market_regime: None` in supervisor | Skip `key_signals` injection and confidence boost; no error |

All fallbacks are silent from the user's perspective — report is sent without regime context.

---

## Test Plan

### `tests/unit/test_hmm_regime.py` (~6 tests)

| Test | Scenario | Assertion |
|---|---|---|
| `test_valid_input_returns_regime_dict` | 60 candles | Returns dict with `regime` in `{"bull_trending", "ranging", "bear_trending"}` |
| `test_short_input_returns_none` | < 30 candles | Returns `None` |
| `test_import_error_returns_none` | mock `ImportError` on hmmlearn | Returns `None`; no exception propagated |
| `test_regime_label_mapping` | controlled input with clear trend | Highest mean return state → `bull_trending` |
| `test_does_not_mutate_input` | 60 candles | Input list unchanged after call |
| `test_deterministic_with_random_state` | same input, called twice | Same `regime` both times |

### `tests/unit/test_market_structure_analyzer.py` (add ~3 tests)

| Test | Scenario | Assertion |
|---|---|---|
| `test_ml_enabled_includes_market_regime` | `ML_ENABLED=True`, 60 candles | `market_regime` field present and not None |
| `test_ml_disabled_market_regime_is_none` | `ML_ENABLED=False` | `market_regime` is None; `detect_hmm_regime` not called |
| `test_hmm_failure_does_not_propagate` | `detect_hmm_regime` raises | `market_regime: None`; no exception from analyzer |

### `tests/unit/test_supervisor.py` (add ~3 tests)

| Test | Scenario | Assertion |
|---|---|---|
| `test_aligned_regime_adds_signal_and_boosts_confidence` | `market_regime={"regime": "bull_trending"}`, bias=`"bullish"` | `"Market Regime Context: bull_trending"` in `key_signals`; confidence += 0.05 |
| `test_misaligned_regime_adds_signal_no_boost` | `market_regime={"regime": "ranging"}`, bias=`"bullish"` | Label in `key_signals`; confidence unchanged |
| `test_none_regime_no_injection` | `market_regime=None` | `key_signals` unchanged; confidence unchanged |

---

## Out of Scope

- Regime sequence history (only current regime exposed)
- Persisted/trained model (stateless: fit fresh each run)
- Monte Carlo integration (separate `MONTE_CARLO_ENABLED` gate)
- `/history` regime trend display
- More than 3 states
