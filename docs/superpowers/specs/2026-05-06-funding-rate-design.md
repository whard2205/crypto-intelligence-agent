# Phase 6 — Funding Rate Analysis

**Date:** 2026-05-06
**Status:** Approved, pending implementation

---

## Overview

Add Binance perpetual futures funding rate as a 5th parallel data source in the pipeline. Funding rate measures whether longs or shorts are paying premium — an extreme positive rate signals longs are overextended (bearish risk), an extreme negative rate signals shorts are overextended (bullish risk). The signal flows through the existing risk analyzer and appears in `key_signals`, `risk_warnings`, and `funding_source` on every report.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Pipeline placement | New 5th parallel collector node | Consistent with existing collector pattern; independently testable |
| Thresholds | Two-level: moderate `> 0.05%`, extreme `> 0.15%` | Distinguishes "crowded" from "overextended" — more actionable than single threshold |
| Mock fallback | `MockFundingRateAdapter` | Consistent with all other adapters; demo works in `MOCK_MODE=true` |
| Unavailable data shape | `None`, not `{}` | Semantically unambiguous; empty dict is ambiguous between "empty", "missing", "unavailable" |
| Summary TypedDict | `FundingRateSummary` TypedDict | Explicit field types; cleaner than raw dict even though other summaries use plain dict |
| Signal routing | `risk_analyzer` → `supervisor` | Funding rate is a risk signal; consistent with `risk_analyzer` responsibility |
| `funding_source` | `"binance"` / `"mock"` / `"unavailable"` | `"unavailable"` is distinct from `"unknown"` — data actively missing vs. source unidentified |

---

## Thresholds

Funding rate stored as raw decimal (0.00080 = 0.08%):

| `abs(rate)` | Label | `risk_score` impact | Message |
|---|---|---|---|
| `>= 0.0015` | extreme | +2 | `"Extreme funding rate {rate:+.3%} — {direction} overextended"` |
| `>= 0.0005` | moderate | +1 | `"Elevated funding rate {rate:+.3%} — {direction} crowded"` |
| `< 0.0005` | neutral | 0 | No signal generated |

Thresholds are inclusive (`>=`). `direction` = `"longs"` when `rate > 0`, `"shorts"` when `rate < 0`.

---

## Files

### New files

| File | Purpose |
|---|---|
| `data_sources/binance/binance_funding_rate.py` | Binance futures funding rate adapter |
| `data_sources/mock/mock_funding_rate.py` | Mock adapter for dev/test/demo |
| `agents/collectors/funding_rate_collector.py` | Collector node factory |
| `tests/unit/test_funding_rate_adapter.py` | Adapter unit tests |
| `tests/unit/test_risk_analyzer_funding.py` | Risk analyzer threshold tests |
| `tests/unit/test_supervisor_funding.py` | Supervisor key_signals + funding_source tests |

### Edited files

| File | Change |
|---|---|
| `data_sources/factory.py` | Wire `funding_rate_adapter` per environment |
| `graph/state.py` | Add `FundingRateSummary` TypedDict; add `funding_rate_data` to `AgentState`; add `funding_rate_summary` to `NormalizedMarketContext`; add `funding_source` to `IntelligenceReport` |
| `graph/aggregator.py` | Extract `funding_rate_summary` from `funding_rate_data`; append `funding_unavailable` to data_gaps when None |
| `graph/pipeline.py` | Add `funding_rate_adapter` param; add `collect_funding_rate` node; update 4→5 collector barrier join |
| `agents/analyzers/risk_analyzer.py` | Read `funding_rate_summary`; apply two-level threshold logic |
| `agents/supervisor.py` | Add funding rate key_signal; add `funding_source` to report |
| `api/schemas.py` | Add `funding_source: str = "unavailable"` to `IntelligenceReportResponse` |
| `publishers/telegram_publisher.py` | Add `| Funding: {funding_source}` to footer |

---

## Data Shapes

### `BinanceFundingRateAdapter.fetch()` return

```python
{
    "symbol":       "BTCUSDT",
    "funding_rate": 0.00080,              # float parsed from "fundingRate" string
    "funding_time": "2026-05-06T08:00:00Z",  # ISO UTC string parsed from fundingTime ms timestamp; "" if absent
    "source":       "binance",
}
# Returns None when:
#   - symbol not found in futures (404)
#   - Binance returns empty list []
# Raises on other HTTP errors (FallbackAdapter catches)
```

**Parsing rules:**
- `fundingRate`: cast string `"0.00080000"` → `float(0.00080)`
- `fundingTime`: millisecond int timestamp → `datetime.utcfromtimestamp(ms/1000).isoformat() + "Z"`; empty string if key absent

### `MockFundingRateAdapter` values

```python
BTCUSDT  →  0.00080   # 0.08% — moderate longs
ETHUSDT  →  -0.00060  # -0.06% — moderate shorts
default  →  0.00010   # neutral
```

### `FundingRateSummary` TypedDict

```python
class FundingRateSummary(TypedDict):
    rate:         float
    funding_time: str
    source:       str
```

### `NormalizedMarketContext` addition

```python
funding_rate_summary: Optional[FundingRateSummary]
# None when funding data is unavailable
```

### `IntelligenceReport` addition

```python
funding_source: str   # "binance" | "mock" | "unavailable"
```

---

## Factory Routing

```
MOCK_MODE=true                    → MockFundingRateAdapter()
MOCK_MODE=false + dev/test        → FallbackAdapter([BinanceFundingRateAdapter(), MockFundingRateAdapter()])
MOCK_MODE=false + production      → BinanceFundingRateAdapter()  # None → data_gaps, no mock fallback
```

---

## Pipeline Change

```
Before: START → [collect_price, collect_news, collect_onchain, collect_social]
                  ↓ barrier join (4)
                aggregate_raw → ...

After:  START → [collect_price, collect_news, collect_onchain, collect_social, collect_funding_rate]
                  ↓ barrier join (5)
                aggregate_raw → ...
```

`build_graph()` signature change:
```python
def build_graph(
    settings:              Settings,
    price_adapter:         DataSourceAdapter,
    news_adapter:          DataSourceAdapter,
    onchain_adapter:       DataSourceAdapter,
    social_adapter:        DataSourceAdapter,
    funding_rate_adapter:  DataSourceAdapter,   # new
):
```

---

## Aggregation Logic

```python
funding_rate_data = state.get("funding_rate_data")

if funding_rate_data is not None:
    funding_rate_summary: Optional[FundingRateSummary] = {
        "rate":         funding_rate_data["funding_rate"],
        "funding_time": funding_rate_data.get("funding_time", ""),
        "source":       funding_rate_data.get("source", "unknown"),
    }
else:
    funding_rate_summary = None
    # append "funding_unavailable" to data_gaps (does NOT block report)
```

---

## Risk Analyzer Logic

```python
funding = context.get("funding_rate_summary")   # Optional[FundingRateSummary]

if funding is not None:
    rate      = funding["rate"]
    abs_rate  = abs(rate)
    direction = "longs" if rate > 0 else "shorts"

    if abs_rate >= 0.0015:
        risk_factors.append(f"Extreme funding rate {rate:+.3%} — {direction} overextended")
        risk_score += 2
    elif abs_rate >= 0.0005:
        risk_factors.append(f"Elevated funding rate {rate:+.3%} — {direction} crowded")
        risk_score += 1
# if funding is None: no signal, no error
```

---

## Supervisor Logic

```python
# key_signals (after RSI line)
funding = context.get("funding_rate_summary")
if funding is not None and abs(funding["rate"]) >= 0.0005:
    direction = "longs" if funding["rate"] > 0 else "shorts"
    key_signals.append(f"Funding rate {funding['rate']:+.3%} ({direction} crowded)")

# funding_source for provenance
funding_source = funding["source"] if funding is not None else "unavailable"
```

---

## Test Plan

### `tests/unit/test_funding_rate_adapter.py`

| Test | Scenario |
|---|---|
| `test_binance_adapter_success` | Happy path → correct rate, funding_time, source |
| `test_binance_adapter_empty_list` | Binance returns `[]` → `None` |
| `test_binance_adapter_404_returns_none` | Non-futures symbol → `None`, no raise |
| `test_binance_adapter_http_error_raises` | 503 → raises `HTTPStatusError` |
| `test_mock_adapter_btcusdt` | BTCUSDT → rate=0.00080, source="mock" |
| `test_mock_adapter_ethusdt` | ETHUSDT → rate=-0.00060 |
| `test_mock_adapter_unknown_symbol` | Unknown → rate=0.00010 (neutral default) |
| `test_fallback_uses_mock_when_binance_fails` | Binance raises → FallbackAdapter returns mock |

### `tests/unit/test_risk_analyzer_funding.py`

Assert on public output only (`risk_level`, `risk_factors`).

| Test | Input rate | Expected |
|---|---|---|
| `test_extreme_positive_rate` | +0.0018 | "Extreme...longs overextended" in risk_factors; risk_level elevated |
| `test_moderate_positive_rate` | +0.0008 | "Elevated...longs crowded" in risk_factors |
| `test_extreme_negative_rate` | -0.0020 | "Extreme...shorts overextended" in risk_factors |
| `test_moderate_negative_rate` | -0.0006 | "Elevated...shorts crowded" in risk_factors |
| `test_neutral_rate_no_signal` | +0.0001 | No funding string in risk_factors |
| `test_missing_funding_summary` | `None` | No error; no funding string in risk_factors |
| `test_boundary_moderate_positive` | +0.0005 (exact) | "Elevated...longs crowded" in risk_factors |
| `test_boundary_moderate_negative` | -0.0005 (exact) | "Elevated...shorts crowded" in risk_factors |
| `test_boundary_extreme_positive` | +0.0015 (exact) | "Extreme...longs overextended" in risk_factors |
| `test_boundary_extreme_negative` | -0.0015 (exact) | "Extreme...shorts overextended" in risk_factors |

### `tests/unit/test_supervisor_funding.py`

| Test | Scenario | Assertion |
|---|---|---|
| `test_funding_signal_in_key_signals` | moderate rate | "Funding rate" in key_signals |
| `test_neutral_funding_not_in_key_signals` | neutral rate | no "Funding rate" in key_signals |
| `test_funding_source_binance` | source="binance" | `funding_source == "binance"` |
| `test_funding_source_unavailable` | `funding_rate_summary=None` | `funding_source == "unavailable"` |

### `tests/unit/test_aggregator.py` additions

| Test | Scenario | Assertion |
|---|---|---|
| `test_aggregate_includes_funding_summary` | `funding_rate_data` present | `funding_rate_summary` in context with correct rate |
| `test_aggregate_funding_none_when_missing` | `funding_rate_data=None` | `funding_rate_summary is None`; `"funding_unavailable"` in data_gaps |

### `tests/unit/test_funding_rate_collector.py`

| Test | Scenario | Assertion |
|---|---|---|
| `test_collector_success` | adapter returns data | `state["funding_rate_data"]` set |
| `test_collector_adapter_returns_none` | adapter returns `None` | `"funding_unavailable"` in data_gaps; no crash |
| `test_collector_adapter_raises` | adapter raises | `"funding_unavailable"` in data_gaps; no crash |

### `tests/integration/test_pipeline.py` additions

| Test | Scenario | Assertion |
|---|---|---|
| `test_pipeline_mock_includes_funding_source` | full run with MockFundingRateAdapter | `report["funding_source"] == "mock"` |
| `test_pipeline_mock_btcusdt_funding_signal` | BTCUSDT mock rate=0.00080 (moderate) | "Funding rate" in `report["key_signals"]` |

### `tests/integration/test_api.py` addition

| Test | Assertion |
|---|---|
| `test_report_response_includes_funding_source` | `response.json()["funding_source"]` present and is a string |

---

## Telegram Footer

Update `publishers/telegram_publisher.py` footer line:

```
Before: Engine: rule-based  |  Price: binance  |  News: rss
After:  Engine: rule-based  |  Price: binance  |  News: rss  |  Funding: binance
```

`funding_source` value comes from `report["funding_source"]`. No other Telegram formatting changes needed.

---

## Collector Safety

`make_funding_rate_collector` wraps the adapter call in `try/except` — unlike `price_collector` (where failure is fatal). Funding rate is supplementary data; a crash must not block the report.

```python
def make_funding_rate_collector(adapter: DataSourceAdapter):
    async def collect_funding_rate(state: AgentState) -> dict:
        try:
            result = await adapter.fetch(state["symbol"])
            if result is None:
                return {"data_gaps": ["funding_unavailable"]}
            return {"funding_rate_data": result}
        except Exception:
            return {"data_gaps": ["funding_unavailable"]}
    return collect_funding_rate
```

---

## Out of Scope

- HMM regime detection
- APScheduler (Phase 6 scheduler)
- Historical funding rate (only latest rate needed)
- Funding rate chart / visualization
- XGBoost, Monte Carlo, Claude integration
