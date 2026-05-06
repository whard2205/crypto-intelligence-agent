# Phase 6 — Funding Rate Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Binance perpetual futures funding rate as a 5th parallel collector, route the signal through the risk analyzer, and surface it in `key_signals`, `risk_warnings`, and `funding_source` on every report.

**Architecture:** New `BinanceFundingRateAdapter` + `MockFundingRateAdapter` follow the existing adapter/fallback pattern. A new `collect_funding_rate` node runs in parallel with the existing 4 collectors. `aggregate_raw` extracts a `FundingRateSummary` TypedDict into `NormalizedMarketContext`. The risk analyzer applies two-level thresholds (moderate ≥ 0.05%, extreme ≥ 0.15%); the supervisor adds the key signal and `funding_source` provenance.

**Tech Stack:** httpx (async HTTP), respx (test mocking), pytest-asyncio, existing LangGraph StateGraph, pydantic for API schema.

**Spec:** `docs/superpowers/specs/2026-05-06-funding-rate-design.md`

---

## File Map

### New files
| File | Responsibility |
|---|---|
| `data_sources/mock/mock_funding_rate.py` | Deterministic mock adapter — BTCUSDT/ETHUSDT/default values |
| `data_sources/binance/binance_funding_rate.py` | Fetches `/fapi/v1/fundingRate`, parses string→float and ms→ISO UTC |
| `agents/collectors/funding_rate_collector.py` | Collector node factory with try/except (supplementary data) |
| `tests/unit/test_funding_rate_adapter.py` | Mock + Binance adapter tests |
| `tests/unit/test_funding_rate_collector.py` | Collector safety tests |
| `tests/unit/test_risk_analyzer_funding.py` | Threshold + boundary tests |
| `tests/unit/test_supervisor_funding.py` | key_signals + funding_source tests |

### Modified files
| File | Change |
|---|---|
| `graph/state.py` | Add `FundingRateSummary` TypedDict; `funding_rate_data` in `AgentState`; `funding_rate_summary` in `NormalizedMarketContext`; `funding_source` in `IntelligenceReport` |
| `tests/conftest.py` | Add `funding_rate_data: None` to `make_state()` |
| `graph/aggregator.py` | Extract `funding_rate_summary`; pass `funding_unavailable` gap when None |
| `graph/pipeline.py` | `funding_rate_adapter` param; 5th node; 4→5 barrier join; `build_pipeline` update |
| `data_sources/factory.py` | Wire `funding_rate_adapter` per environment |
| `api/routes/report.py` | Add `funding_rate_data: None` to `_make_initial_state` |
| `agents/analyzers/risk_analyzer.py` | Two-level threshold logic |
| `agents/supervisor.py` | Funding key_signal + `funding_source` provenance |
| `api/schemas.py` | `funding_source: str = "unavailable"` |
| `publishers/telegram_publisher.py` | Footer: `| Funding: {funding_source}` |
| `tests/unit/test_aggregator.py` | 2 new tests |
| `tests/integration/test_pipeline.py` | Update fixtures + 2 new tests |
| `tests/integration/test_api.py` | Update required fields + 1 new test |

---

## Task 1: Mock funding rate adapter

**Files:**
- Create: `data_sources/mock/mock_funding_rate.py`
- Create: `tests/unit/test_funding_rate_adapter.py` (mock tests only for now)

- [ ] **Step 1: Write the failing mock adapter tests**

```python
# tests/unit/test_funding_rate_adapter.py
import pytest
from data_sources.mock.mock_funding_rate import MockFundingRateAdapter


async def test_mock_adapter_btcusdt():
    result = await MockFundingRateAdapter().fetch("BTCUSDT")
    assert result is not None
    assert result["funding_rate"] == pytest.approx(0.00080)
    assert result["source"] == "mock"
    assert "funding_time" in result
    assert result["symbol"] == "BTCUSDT"


async def test_mock_adapter_ethusdt():
    result = await MockFundingRateAdapter().fetch("ETHUSDT")
    assert result is not None
    assert result["funding_rate"] == pytest.approx(-0.00060)
    assert result["source"] == "mock"


async def test_mock_adapter_unknown_symbol_returns_neutral_default():
    result = await MockFundingRateAdapter().fetch("SOLUSDT")
    assert result is not None
    assert result["funding_rate"] == pytest.approx(0.00010)
    assert result["source"] == "mock"
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/unit/test_funding_rate_adapter.py -v
```
Expected: `ModuleNotFoundError: No module named 'data_sources.mock.mock_funding_rate'`

- [ ] **Step 3: Create the mock adapter**

```python
# data_sources/mock/mock_funding_rate.py
from __future__ import annotations
from data_sources.base import DataSourceAdapter

_FUNDING: dict[str, dict] = {
    "BTCUSDT": {"symbol": "BTCUSDT", "funding_rate":  0.00080, "funding_time": "", "source": "mock"},
    "ETHUSDT": {"symbol": "ETHUSDT", "funding_rate": -0.00060, "funding_time": "", "source": "mock"},
}
_DEFAULT = {"funding_rate": 0.00010, "funding_time": "", "source": "mock"}


class MockFundingRateAdapter(DataSourceAdapter):
    source_name = "mock_funding_rate"

    async def fetch(self, symbol: str) -> dict:
        base = _FUNDING.get(symbol, {**_DEFAULT, "symbol": symbol})
        return {**base, "symbol": symbol}
```

- [ ] **Step 4: Run to confirm pass**

```
uv run pytest tests/unit/test_funding_rate_adapter.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```
git add data_sources/mock/mock_funding_rate.py tests/unit/test_funding_rate_adapter.py
git commit -m "feat: add MockFundingRateAdapter with BTCUSDT/ETHUSDT values"
```

---

## Task 2: Binance funding rate adapter

**Files:**
- Create: `data_sources/binance/binance_funding_rate.py`
- Modify: `tests/unit/test_funding_rate_adapter.py` (append Binance tests)

- [ ] **Step 1: Append Binance tests to the test file**

```python
# Append to tests/unit/test_funding_rate_adapter.py

import httpx
import respx
from data_sources.binance.binance_funding_rate import BinanceFundingRateAdapter
from data_sources.base import FallbackAdapter

_FAPI_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def _funding_payload(rate: str = "0.00080000", ts: int = 1_746_518_400_000) -> list:
    return [{"symbol": "BTCUSDT", "fundingTime": ts, "fundingRate": rate, "markPrice": "95000.00"}]


async def test_binance_adapter_success():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(200, json=_funding_payload()))
        result = await BinanceFundingRateAdapter().fetch("BTCUSDT")

    assert result is not None
    assert result["symbol"] == "BTCUSDT"
    assert result["funding_rate"] == pytest.approx(0.00080)
    assert result["source"] == "binance"
    assert result["funding_time"].endswith("Z")   # ISO UTC string


async def test_binance_adapter_empty_list_returns_none():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(200, json=[]))
        result = await BinanceFundingRateAdapter().fetch("BTCUSDT")
    assert result is None


async def test_binance_adapter_404_returns_none():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(404))
        result = await BinanceFundingRateAdapter().fetch("BTCUSDT")
    assert result is None


async def test_binance_adapter_503_raises():
    with respx.mock:
        respx.get(_FAPI_URL).mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            await BinanceFundingRateAdapter().fetch("BTCUSDT")


async def test_fallback_uses_mock_when_binance_fails():
    class _Failing(DataSourceAdapter):
        source_name = "binance_funding_rate"
        async def fetch(self, symbol: str):
            raise RuntimeError("network unreachable")

    adapter = FallbackAdapter([_Failing(), MockFundingRateAdapter()])
    result  = await adapter.fetch("BTCUSDT")
    assert result is not None
    assert result["source"] == "mock"
```

- [ ] **Step 2: Run to confirm new tests fail**

```
uv run pytest tests/unit/test_funding_rate_adapter.py -v -k "binance or fallback"
```
Expected: `ImportError` for `BinanceFundingRateAdapter`

- [ ] **Step 3: Create the Binance adapter**

```python
# data_sources/binance/binance_funding_rate.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import httpx
from data_sources.base import DataSourceAdapter

_FAPI_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
_TIMEOUT  = 10.0


class BinanceFundingRateAdapter(DataSourceAdapter):
    """Fetch latest perpetual futures funding rate from Binance. No API key required."""

    source_name = "binance_funding_rate"

    async def fetch(self, symbol: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_FAPI_URL, params={"symbol": symbol, "limit": 1})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()

        data = resp.json()
        if not data:
            return None

        item = data[0]
        funding_rate = float(item["fundingRate"])

        ts_ms = item.get("fundingTime")
        if ts_ms:
            funding_time = (
                datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
        else:
            funding_time = ""

        return {
            "symbol":       symbol,
            "funding_rate": funding_rate,
            "funding_time": funding_time,
            "source":       "binance",
        }
```

- [ ] **Step 4: Run all adapter tests**

```
uv run pytest tests/unit/test_funding_rate_adapter.py -v
```
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```
git add data_sources/binance/binance_funding_rate.py tests/unit/test_funding_rate_adapter.py
git commit -m "feat: add BinanceFundingRateAdapter with fundingRate/fundingTime parsing"
```

---

## Task 3: State TypedDicts

**Files:**
- Modify: `graph/state.py`
- Modify: `tests/conftest.py`

No standalone test for this task — downstream tests will cover it.

- [ ] **Step 1: Update `graph/state.py`**

Add `FundingRateSummary` TypedDict at the top (after existing imports), add `funding_rate_data` to `AgentState`, add `funding_rate_summary` to `NormalizedMarketContext`, add `funding_source` to `IntelligenceReport`:

```python
# graph/state.py
from __future__ import annotations
import operator
from typing import Annotated, Literal, Optional, Union
from typing import TypedDict


class FundingRateSummary(TypedDict):
    rate:         float
    funding_time: str
    source:       str


class NormalizedMarketContext(TypedDict):
    """Produced by aggregate_raw. All downstream nodes read only from this."""
    symbol:               str
    price_summary:        dict
    news_items:           list[dict]
    onchain_summary:      dict
    social_summary:       dict
    data_gaps:            list[str]
    price_source:         str
    news_source:          str
    funding_rate_summary: Optional[FundingRateSummary]


class AnalysisResult(TypedDict):
    """Produced by merge_analysis. Combines three analyzer outputs."""
    sentiment_score:   Optional[float]
    sentiment_label:   Optional[str]
    sentiment_drivers: Optional[list[str]]
    market_structure:  Optional[dict]
    risk_level:        Optional[str]
    risk_factors:      Optional[list[str]]


class IntelligenceReport(TypedDict):
    """Produced by supervisor on success."""
    run_id:           str
    symbol:           str
    requested_at:     str
    generated_at:     str
    market_bias:      Literal["bullish", "bearish", "neutral"]
    confidence_score: float
    key_signals:      list[str]
    risk_warnings:    list[str]
    narrative:        str
    data_gaps:        list[str]
    error:            Optional[str]
    llm_used:         bool
    market_structure: Optional[dict]
    price_source:     str
    news_source:      str
    analysis_engine:  str
    funding_source:   str


class ErrorReport(TypedDict):
    """Produced by aggregate_raw when price_data is None."""
    run_id:       str
    symbol:       str
    requested_at: str
    generated_at: str
    error:        str
    data_gaps:    list[str]


class AgentState(TypedDict):
    # Pipeline trigger fields
    run_id:       str
    symbol:       str
    requested_at: str

    # Raw collector outputs
    price_data:        Optional[dict]
    news_data:         Annotated[list, operator.add]
    onchain_data:      Optional[dict]
    social_data:       Optional[dict]
    funding_rate_data: Optional[dict]

    # Post-aggregation context
    context: Optional[NormalizedMarketContext]

    # Independent analyzer outputs (written in parallel, never conflict)
    sentiment_analysis:        Optional[dict]
    market_structure_analysis: Optional[dict]
    risk_analysis:             Optional[dict]

    # Merged analysis (written by merge_analysis)
    analysis: Optional[AnalysisResult]

    # Final report (IntelligenceReport or ErrorReport)
    report: Optional[Union[IntelligenceReport, ErrorReport]]

    # Accumulator fields — reducer-safe for parallel writes
    data_gaps: Annotated[list[str], operator.add]
    errors:    Annotated[list[str], operator.add]
```

- [ ] **Step 2: Add `funding_rate_data` to `make_state()` in conftest**

```python
# tests/conftest.py — update make_state()
def make_state(symbol: str = "BTCUSDT", **overrides) -> dict:
    base = {
        "run_id":       str(uuid.uuid4()),
        "symbol":       symbol,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "price_data":   None,
        "news_data":    [],
        "onchain_data": None,
        "social_data":  None,
        "funding_rate_data": None,       # new
        "context":      None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":     None,
        "report":       None,
        "data_gaps":    [],
        "errors":       [],
    }
    return {**base, **overrides}
```

- [ ] **Step 3: Verify existing tests still pass**

```
uv run pytest tests/ -v --tb=short
```
Expected: all previously passing tests still PASS (no downstream breakage yet since aggregator/pipeline not updated)

- [ ] **Step 4: Commit**

```
git add graph/state.py tests/conftest.py
git commit -m "feat: add FundingRateSummary TypedDict and funding_rate_data to AgentState"
```

---

## Task 4: Funding rate collector

**Files:**
- Create: `agents/collectors/funding_rate_collector.py`
- Create: `tests/unit/test_funding_rate_collector.py`

- [ ] **Step 1: Write failing collector tests**

```python
# tests/unit/test_funding_rate_collector.py
import pytest
from data_sources.base import DataSourceAdapter
from agents.collectors.funding_rate_collector import make_funding_rate_collector
from tests.conftest import make_state


class _SuccessAdapter(DataSourceAdapter):
    source_name = "mock"
    async def fetch(self, symbol: str) -> dict:
        return {"symbol": symbol, "funding_rate": 0.00080, "funding_time": "", "source": "mock"}


class _NoneAdapter(DataSourceAdapter):
    source_name = "mock"
    async def fetch(self, symbol: str):
        return None


class _RaisingAdapter(DataSourceAdapter):
    source_name = "mock"
    async def fetch(self, symbol: str):
        raise RuntimeError("network error")


async def test_collector_success():
    node   = make_funding_rate_collector(_SuccessAdapter())
    result = await node(make_state())
    assert "funding_rate_data" in result
    assert result["funding_rate_data"]["funding_rate"] == pytest.approx(0.00080)


async def test_collector_adapter_returns_none_adds_data_gap():
    node   = make_funding_rate_collector(_NoneAdapter())
    result = await node(make_state())
    assert "funding_rate_data" not in result
    assert "funding_unavailable" in result.get("data_gaps", [])


async def test_collector_adapter_raises_adds_data_gap_no_crash():
    node   = make_funding_rate_collector(_RaisingAdapter())
    result = await node(make_state())
    assert "funding_rate_data" not in result
    assert "funding_unavailable" in result.get("data_gaps", [])
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/unit/test_funding_rate_collector.py -v
```
Expected: `ImportError: cannot import name 'make_funding_rate_collector'`

- [ ] **Step 3: Create the collector**

```python
# agents/collectors/funding_rate_collector.py
from __future__ import annotations
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


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

- [ ] **Step 4: Run to confirm pass**

```
uv run pytest tests/unit/test_funding_rate_collector.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```
git add agents/collectors/funding_rate_collector.py tests/unit/test_funding_rate_collector.py
git commit -m "feat: add make_funding_rate_collector with graceful failure handling"
```

---

## Task 5: Aggregator changes

**Files:**
- Modify: `graph/aggregator.py`
- Modify: `tests/unit/test_aggregator.py` (append 2 tests)

- [ ] **Step 1: Append 2 tests to `tests/unit/test_aggregator.py`**

```python
# Append to tests/unit/test_aggregator.py

async def test_aggregate_includes_funding_summary():
    state = _state_with_price()
    state["funding_rate_data"] = {
        "symbol": "BTCUSDT", "funding_rate": 0.00080,
        "funding_time": "2026-05-06T08:00:00Z", "source": "binance",
    }
    result = await aggregate_raw(state)
    ctx = result["context"]
    assert ctx["funding_rate_summary"] is not None
    assert ctx["funding_rate_summary"]["rate"] == pytest.approx(0.00080)
    assert ctx["funding_rate_summary"]["source"] == "binance"
    assert ctx["funding_rate_summary"]["funding_time"] == "2026-05-06T08:00:00Z"


async def test_aggregate_funding_none_when_missing():
    state = _state_with_price()
    # funding_rate_data is already None in make_state() default
    result = await aggregate_raw(state)
    ctx = result["context"]
    assert ctx["funding_rate_summary"] is None
    assert "funding_unavailable" in ctx["data_gaps"]
```

- [ ] **Step 2: Run to confirm new tests fail**

```
uv run pytest tests/unit/test_aggregator.py -v -k "funding"
```
Expected: `KeyError: 'funding_rate_summary'`

- [ ] **Step 3: Update `graph/aggregator.py`**

Replace the full `aggregate_raw` function (keep `fan_out_analyzers` and `merge_analysis` unchanged):

```python
# graph/aggregator.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from graph.state import AgentState, NormalizedMarketContext, AnalysisResult, FundingRateSummary


async def aggregate_raw(state: AgentState) -> dict:
    price_data        = state.get("price_data")
    news_data         = state.get("news_data") or []
    onchain_data      = state.get("onchain_data")
    social_data       = state.get("social_data")
    funding_rate_data = state.get("funding_rate_data")

    if price_data is None:
        return {
            "report": {
                "run_id":       state["run_id"],
                "symbol":       state["symbol"],
                "requested_at": state["requested_at"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "error":        "Price data unavailable — cannot generate intelligence report",
                "data_gaps":    list(set(state.get("data_gaps", []))),
            }
        }

    price_summary = {
        "price":          price_data.get("price_usd", 0.0),
        "change_24h_pct": price_data.get("change_24h_pct", 0.0),
        "volume_24h":     price_data.get("volume_24h_usd", 0.0),
        "high_24h":       price_data.get("high_24h", 0.0),
        "low_24h":        price_data.get("low_24h", 0.0),
        "ohlcv_24h":      price_data.get("ohlcv_24h", []),
    }

    news_items = [
        {
            "headline":     item.get("title", ""),
            "source":       item.get("source", ""),
            "published_at": item.get("published_at", ""),
            "url":          item.get("url", ""),
        }
        for item in news_data
    ]

    social_summary: dict = {}
    if social_data:
        social_summary = {
            "mention_volume": social_data.get("post_count", 0),
            "sentiment_hint": "neutral",
            "sample_posts":   social_data.get("top_posts", []),
        }

    price_source = price_data.get("source", "unknown")

    if not news_data:
        news_source = "unknown"
    elif all(item.get("source") == "MockNews" for item in news_data):
        news_source = "mock"
    else:
        news_source = "rss"

    funding_rate_summary: Optional[FundingRateSummary]
    if funding_rate_data is not None:
        funding_rate_summary = FundingRateSummary(
            rate=         funding_rate_data["funding_rate"],
            funding_time= funding_rate_data.get("funding_time", ""),
            source=       funding_rate_data.get("source", "unknown"),
        )
    else:
        funding_rate_summary = None

    # Merge data_gaps: from state accumulator + funding gap if unavailable
    all_gaps = list(set(state.get("data_gaps", [])))
    if funding_rate_summary is None and "funding_unavailable" not in all_gaps:
        all_gaps.append("funding_unavailable")

    context: NormalizedMarketContext = {
        "symbol":               state["symbol"],
        "price_summary":        price_summary,
        "news_items":           news_items,
        "onchain_summary":      onchain_data or {},
        "social_summary":       social_summary,
        "data_gaps":            all_gaps,
        "price_source":         price_source,
        "news_source":          news_source,
        "funding_rate_summary": funding_rate_summary,
    }

    return {"context": context}
```

**Note:** `FundingRateSummary(...)` is a TypedDict — instantiated as a regular dict with keyword args.

- [ ] **Step 4: Run aggregator tests**

```
uv run pytest tests/unit/test_aggregator.py -v
```
Expected: all 6 PASSED (4 existing + 2 new)

- [ ] **Step 5: Commit**

```
git add graph/aggregator.py tests/unit/test_aggregator.py
git commit -m "feat: aggregate funding_rate_summary in NormalizedMarketContext"
```

---

## Task 6: Pipeline wiring + factory

**Files:**
- Modify: `graph/pipeline.py`
- Modify: `data_sources/factory.py`
- Modify: `api/routes/report.py`
- Modify: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Update `graph/pipeline.py`**

Add `funding_rate_adapter` parameter, 5th node, update barrier join, update `build_pipeline`:

```python
# graph/pipeline.py
from __future__ import annotations
from langgraph.graph import StateGraph, START, END

from config.settings import Settings
from data_sources.base import DataSourceAdapter
from graph.state import AgentState
from graph.aggregator import aggregate_raw, fan_out_analyzers, merge_analysis
from graph.edges import route_after_aggregate


def build_graph(
    settings:             Settings,
    price_adapter:        DataSourceAdapter,
    news_adapter:         DataSourceAdapter,
    onchain_adapter:      DataSourceAdapter,
    social_adapter:       DataSourceAdapter,
    funding_rate_adapter: DataSourceAdapter,
):
    """Assemble and compile the LangGraph StateGraph."""
    from agents.collectors.price_collector         import make_price_collector
    from agents.collectors.news_collector          import make_news_collector
    from agents.collectors.onchain_collector       import make_onchain_collector
    from agents.collectors.social_collector        import make_social_collector
    from agents.collectors.funding_rate_collector  import make_funding_rate_collector
    from agents.analyzers.sentiment_analyzer       import make_sentiment_analyzer
    from agents.analyzers.market_structure_analyzer import analyze_market_structure
    from agents.analyzers.risk_analyzer            import make_risk_analyzer
    from agents.supervisor                         import make_supervisor

    workflow = StateGraph(AgentState)

    # --- Nodes ---
    workflow.add_node("collect_price",         make_price_collector(price_adapter))
    workflow.add_node("collect_news",          make_news_collector(news_adapter))
    workflow.add_node("collect_onchain",       make_onchain_collector(onchain_adapter))
    workflow.add_node("collect_social",        make_social_collector(social_adapter))
    workflow.add_node("collect_funding_rate",  make_funding_rate_collector(funding_rate_adapter))
    workflow.add_node("aggregate_raw",         aggregate_raw)
    workflow.add_node("fan_out_analyzers",     fan_out_analyzers)
    workflow.add_node("analyze_sentiment",         make_sentiment_analyzer(settings))
    workflow.add_node("analyze_market_structure",  analyze_market_structure)
    workflow.add_node("analyze_risk",              make_risk_analyzer(settings))
    workflow.add_node("merge_analysis",  merge_analysis)
    workflow.add_node("supervisor",      make_supervisor(settings))
    workflow.add_node("error_exit",      lambda state: {})

    # --- Edges ---
    workflow.add_edge(START, "collect_price")
    workflow.add_edge(START, "collect_news")
    workflow.add_edge(START, "collect_onchain")
    workflow.add_edge(START, "collect_social")
    workflow.add_edge(START, "collect_funding_rate")

    # Barrier join: all 5 collectors → aggregate_raw
    workflow.add_edge(
        ["collect_price", "collect_news", "collect_onchain",
         "collect_social", "collect_funding_rate"],
        "aggregate_raw",
    )

    workflow.add_conditional_edges(
        "aggregate_raw",
        route_after_aggregate,
        {"error_exit": "error_exit", "fan_out_analyzers": "fan_out_analyzers"},
    )

    workflow.add_edge("fan_out_analyzers", "analyze_sentiment")
    workflow.add_edge("fan_out_analyzers", "analyze_market_structure")
    workflow.add_edge("fan_out_analyzers", "analyze_risk")

    workflow.add_edge(
        ["analyze_sentiment", "analyze_market_structure", "analyze_risk"],
        "merge_analysis",
    )

    workflow.add_edge("merge_analysis", "supervisor")
    workflow.add_edge("supervisor", END)
    workflow.add_edge("error_exit", END)

    return workflow.compile()


def build_pipeline(settings: Settings):
    """Convenience wrapper: wire mock adapters."""
    from data_sources.mock.mock_price        import MockPriceAdapter
    from data_sources.mock.mock_news         import MockNewsAdapter
    from data_sources.mock.mock_onchain      import MockOnChainAdapter
    from data_sources.mock.mock_social       import MockSocialAdapter
    from data_sources.mock.mock_funding_rate import MockFundingRateAdapter

    return build_graph(
        settings,
        price_adapter=        MockPriceAdapter(),
        news_adapter=         MockNewsAdapter(),
        onchain_adapter=      MockOnChainAdapter(),
        social_adapter=       MockSocialAdapter(),
        funding_rate_adapter= MockFundingRateAdapter(),
    )
```

- [ ] **Step 2: Update `data_sources/factory.py`**

```python
# data_sources/factory.py
from __future__ import annotations
from config.settings import Settings
from data_sources.base import DataSourceAdapter, FallbackAdapter
from data_sources.mock.mock_price        import MockPriceAdapter
from data_sources.mock.mock_news         import MockNewsAdapter
from data_sources.mock.mock_onchain      import MockOnChainAdapter
from data_sources.mock.mock_social       import MockSocialAdapter
from data_sources.mock.mock_funding_rate import MockFundingRateAdapter


def build_adapters(settings: Settings) -> dict[str, DataSourceAdapter]:
    """Return adapters for build_graph.

    Price routing:
      MOCK_MODE=true              → mock only
      MOCK_MODE=false + dev/test  → Binance → CoinGecko → mock
      MOCK_MODE=false + production → Binance → CoinGecko (no mock fallback)

    News routing:
      MOCK_MODE=true              → mock only
      MOCK_MODE=false + dev/test  → RSS → mock
      MOCK_MODE=false + production → RSS only (no mock fallback)

    Funding rate routing:
      MOCK_MODE=true              → mock only
      MOCK_MODE=false + dev/test  → Binance futures → mock
      MOCK_MODE=false + production → Binance futures only (no mock fallback)
    """
    if settings.MOCK_MODE:
        price_adapter:        DataSourceAdapter = MockPriceAdapter()
        news_adapter:         DataSourceAdapter = MockNewsAdapter()
        funding_rate_adapter: DataSourceAdapter = MockFundingRateAdapter()
    else:
        from data_sources.binance.binance_price       import BinancePriceAdapter
        from data_sources.coingecko.coingecko_price   import CoinGeckoPriceAdapter
        from data_sources.news.rss_feed               import RSSFeedAdapter
        from data_sources.binance.binance_funding_rate import BinanceFundingRateAdapter

        if settings.ENV in ("development", "test"):
            price_adapter = FallbackAdapter(
                [BinancePriceAdapter(), CoinGeckoPriceAdapter(), MockPriceAdapter()]
            )
            news_adapter = FallbackAdapter([RSSFeedAdapter(), MockNewsAdapter()])
            funding_rate_adapter = FallbackAdapter(
                [BinanceFundingRateAdapter(), MockFundingRateAdapter()]
            )
        else:
            price_adapter = FallbackAdapter(
                [BinancePriceAdapter(), CoinGeckoPriceAdapter()]
            )
            news_adapter         = RSSFeedAdapter()
            funding_rate_adapter = BinanceFundingRateAdapter()

    return {
        "price_adapter":        price_adapter,
        "news_adapter":         news_adapter,
        "onchain_adapter":      MockOnChainAdapter(),
        "social_adapter":       MockSocialAdapter(),
        "funding_rate_adapter": funding_rate_adapter,
    }
```

- [ ] **Step 3: Update `api/routes/report.py` — add `funding_rate_data: None` to `_make_initial_state`**

```python
def _make_initial_state(symbol: str) -> dict:
    return {
        "run_id":                    str(uuid.uuid4()),
        "symbol":                    symbol,
        "requested_at":              datetime.now(timezone.utc).isoformat(),
        "price_data":                None,
        "news_data":                 [],
        "onchain_data":              None,
        "social_data":               None,
        "funding_rate_data":         None,      # new
        "context":                   None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":                  None,
        "report":                    None,
        "data_gaps":                 [],
        "errors":                    [],
    }
```

- [ ] **Step 4: Update `tests/integration/test_pipeline.py`**

Update `_initial_state`, `mock_graph` fixture, and the two bare `build_graph` calls:

```python
# tests/integration/test_pipeline.py
import pytest
from unittest.mock import AsyncMock
from config.settings import Settings
from data_sources.base import DataSourceAdapter
from data_sources.mock.mock_funding_rate import MockFundingRateAdapter
from graph.pipeline import build_graph


class _MockAdapter(DataSourceAdapter):
    def __init__(self, name: str, payload):
        self.source_name = name
        self._payload = payload

    async def fetch(self, symbol: str):
        return self._payload


def _initial_state(symbol: str = "BTCUSDT") -> dict:
    from graph.state import AgentState
    import uuid, datetime
    return {
        "run_id":                    str(uuid.uuid4()),
        "symbol":                    symbol,
        "requested_at":              datetime.datetime.now(datetime.UTC).isoformat(),
        "price_data":                None,
        "news_data":                 [],
        "onchain_data":              None,
        "social_data":               None,
        "funding_rate_data":         None,      # new
        "context":                   None,
        "sentiment_analysis":        None,
        "market_structure_analysis": None,
        "risk_analysis":             None,
        "analysis":                  None,
        "report":                    None,
        "data_gaps":                 [],
        "errors":                    [],
    }


def _make_price_payload(symbol: str = "BTCUSDT"):
    import math
    base = 65000.0
    n = 60
    candles = []
    for i in range(n):
        trend = (i / n) * base * 0.065
        cycle = base * 0.014 * math.sin(i * 2 * math.pi / 18)
        close = base + trend + cycle
        candles.append({
            "open": round(close - base * 0.003, 2),
            "high": round(close + base * 0.005, 2),
            "low": round(close - base * 0.005, 2),
            "close": round(close, 2),
            "volume": 500 + i * 10,
        })
    return {
        "symbol": symbol,
        "price_usd": candles[-1]["close"],
        "change_24h_pct": 2.3,
        "volume_24h_usd": 28e9,
        "high_24h": 66000.0,
        "low_24h": 64000.0,
        "ohlcv_24h": candles,
        "source": "mock",
    }


def _mock_funding() -> _MockAdapter:
    return _MockAdapter("mock_funding_rate",
                        {"symbol": "BTCUSDT", "funding_rate": 0.00080,
                         "funding_time": "", "source": "mock"})


@pytest.fixture
def settings_mock():
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


@pytest.fixture
def mock_graph(settings_mock):
    price   = _MockAdapter("mock_price",   _make_price_payload())
    news    = _MockAdapter("mock_news",    [{"title": "BTC rally", "source": "mock",
                                             "published_at": "", "url": ""}])
    onchain = _MockAdapter("mock_onchain", {"network": "bitcoin", "active_addresses_24h": 1_000_000})
    social  = _MockAdapter("mock_social",  {"post_count": 20, "top_posts": [], "source": "mock"})
    funding = _mock_funding()
    return build_graph(settings_mock, price, news, onchain, social, funding)


async def test_full_pipeline_btcusdt(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]

    assert not report.get("error")
    assert report["symbol"] == "BTCUSDT"
    assert report["market_bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= report["confidence_score"] <= 1.0
    assert isinstance(report["key_signals"], list)
    assert len(report["key_signals"]) >= 1
    assert isinstance(report["narrative"], str)
    assert report["llm_used"] is False


async def test_pipeline_returns_error_report_when_price_missing(settings_mock):
    bad_price = _MockAdapter("mock_price", None)
    news      = _MockAdapter("mock_news",    [])
    onchain   = _MockAdapter("mock_onchain", {})
    social    = _MockAdapter("mock_social",  {})
    funding   = _mock_funding()
    graph = build_graph(settings_mock, bad_price, news, onchain, social, funding)

    result = await graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]
    assert "error" in report
    assert report["symbol"] == "BTCUSDT"


async def test_pipeline_continues_when_social_missing(settings_mock):
    price   = _MockAdapter("mock_price",   _make_price_payload())
    news    = _MockAdapter("mock_news",    [{"title": "BTC rally", "source": "mock",
                                             "published_at": "", "url": ""}])
    onchain = _MockAdapter("mock_onchain", {"network": "bitcoin", "active_addresses_24h": 1_000_000})
    social  = _MockAdapter("mock_social",  None)
    funding = _mock_funding()
    graph = build_graph(settings_mock, price, news, onchain, social, funding)

    result = await graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]
    assert not report.get("error")
    assert "social_unavailable" in report.get("data_gaps", [])


async def test_pipeline_full_report_structure(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]

    required_keys = {
        "symbol", "market_bias", "confidence_score",
        "key_signals", "narrative", "llm_used",
        "generated_at", "data_gaps",
    }
    assert required_keys.issubset(report.keys())
    assert isinstance(report["data_gaps"], list)
    assert isinstance(report["generated_at"], str)


async def test_pipeline_mock_includes_funding_source(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]
    assert not report.get("error")
    assert report.get("funding_source") == "mock"


async def test_pipeline_mock_btcusdt_funding_signal(mock_graph):
    result = await mock_graph.ainvoke(_initial_state("BTCUSDT"))
    report = result["report"]
    assert not report.get("error")
    # BTCUSDT mock rate = 0.00080 (moderate) → supervisor adds key_signal
    funding_signals = [s for s in report["key_signals"] if "Funding rate" in s]
    assert len(funding_signals) >= 1
```

- [ ] **Step 5: Run integration pipeline tests**

```
uv run pytest tests/integration/test_pipeline.py -v
```
Expected: tests may fail because `supervisor.py` and `risk_analyzer.py` haven't been updated yet — specifically `funding_source` will be missing from report. That is expected at this stage.

- [ ] **Step 6: Commit partial wiring**

```
git add graph/pipeline.py data_sources/factory.py api/routes/report.py tests/integration/test_pipeline.py
git commit -m "feat: wire funding_rate_adapter as 5th parallel collector in pipeline"
```

---

## Task 7: Risk analyzer

**Files:**
- Create: `tests/unit/test_risk_analyzer_funding.py`
- Modify: `agents/analyzers/risk_analyzer.py`

- [ ] **Step 1: Write failing risk analyzer tests**

```python
# tests/unit/test_risk_analyzer_funding.py
import pytest
from config.settings import Settings
from agents.analyzers.risk_analyzer import make_risk_analyzer
from tests.conftest import make_state


def _make_settings() -> Settings:
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


def _state_with_funding(rate: float) -> dict:
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {"price": 65000.0, "change_24h_pct": 2.0,
                          "volume_24h": 28e9, "high_24h": 66000.0,
                          "low_24h": 64000.0, "ohlcv_24h": []},
        "news_items": [], "onchain_summary": {}, "social_summary": {},
        "data_gaps": [],
        "funding_rate_summary": {"rate": rate, "funding_time": "", "source": "binance"},
    }
    return state


def _state_without_funding() -> dict:
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {"price": 65000.0, "change_24h_pct": 2.0,
                          "volume_24h": 28e9, "high_24h": 66000.0,
                          "low_24h": 64000.0, "ohlcv_24h": []},
        "news_items": [], "onchain_summary": {}, "social_summary": {},
        "data_gaps": [], "funding_rate_summary": None,
    }
    return state


async def test_extreme_positive_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0018))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "longs" in f for f in rf)


async def test_moderate_positive_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0008))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "longs" in f for f in rf)


async def test_extreme_negative_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0020))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "shorts" in f for f in rf)


async def test_moderate_negative_rate_appears_in_risk_factors():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0006))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "shorts" in f for f in rf)


async def test_neutral_rate_no_funding_signal():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0001))
    rf     = result["risk_analysis"]["risk_factors"]
    assert not any("funding rate" in f.lower() for f in rf)


async def test_missing_funding_summary_no_error():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_without_funding())
    assert "risk_analysis" in result
    rf = result["risk_analysis"]["risk_factors"]
    assert not any("funding rate" in f.lower() for f in rf)


# --- Boundary tests (inclusive thresholds) ---

async def test_boundary_moderate_positive():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0005))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "longs" in f for f in rf)


async def test_boundary_moderate_negative():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0005))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Elevated" in f and "shorts" in f for f in rf)


async def test_boundary_extreme_positive():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(+0.0015))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "longs" in f for f in rf)


async def test_boundary_extreme_negative():
    node   = make_risk_analyzer(_make_settings())
    result = await node(_state_with_funding(-0.0015))
    rf     = result["risk_analysis"]["risk_factors"]
    assert any("Extreme" in f and "shorts" in f for f in rf)
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/unit/test_risk_analyzer_funding.py -v
```
Expected: all 10 FAIL — funding logic not implemented yet

- [ ] **Step 3: Update `agents/analyzers/risk_analyzer.py`**

```python
# agents/analyzers/risk_analyzer.py
from __future__ import annotations
from config.settings import Settings
from graph.state import AgentState


def make_risk_analyzer(settings: Settings):
    async def analyze_risk(state: AgentState) -> dict:
        if settings.LLM_ENABLED:
            pass
        return _deterministic_risk(state)
    return analyze_risk


def _deterministic_risk(state: AgentState) -> dict:
    context       = state.get("context") or {}
    price_summary = context.get("price_summary", {})
    onchain       = context.get("onchain_summary", {})
    funding       = context.get("funding_rate_summary")    # Optional[FundingRateSummary]
    data_gaps     = context.get("data_gaps", [])
    risk_factors: list[str] = []
    risk_score = 0

    change = abs(price_summary.get("change_24h_pct", 0.0))
    if change > 10:
        risk_factors.append(f"High price volatility: {change:.1f}% in 24h")
        risk_score += 2
    elif change > 5:
        risk_factors.append(f"Moderate price volatility: {change:.1f}% in 24h")
        risk_score += 1

    if onchain.get("mempool_size", 0) > 100_000:
        risk_factors.append("High mempool congestion detected")
        risk_score += 1

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

    if data_gaps:
        risk_factors.append(f"Incomplete data: {', '.join(data_gaps)}")
        risk_score += 1

    risk_level = "high" if risk_score >= 3 else "medium" if risk_score >= 1 else "low"

    return {
        "risk_analysis": {
            "risk_level":   risk_level,
            "risk_factors": risk_factors or ["No significant risk factors detected"],
        }
    }
```

- [ ] **Step 4: Run risk analyzer tests**

```
uv run pytest tests/unit/test_risk_analyzer_funding.py -v
```
Expected: 10 PASSED

- [ ] **Step 5: Run full unit test suite to confirm no regressions**

```
uv run pytest tests/unit/ -v --tb=short
```
Expected: all PASSED

- [ ] **Step 6: Commit**

```
git add agents/analyzers/risk_analyzer.py tests/unit/test_risk_analyzer_funding.py
git commit -m "feat: add two-level funding rate threshold logic to risk_analyzer"
```

---

## Task 8: Supervisor changes

**Files:**
- Create: `tests/unit/test_supervisor_funding.py`
- Modify: `agents/supervisor.py`

- [ ] **Step 1: Write failing supervisor tests**

```python
# tests/unit/test_supervisor_funding.py
import pytest
from config.settings import Settings
from agents.supervisor import make_supervisor
from tests.conftest import make_state


def _make_settings() -> Settings:
    return Settings(ENV="test", MOCK_MODE=True, LLM_ENABLED=False)


def _state_with_context(funding_rate_summary) -> dict:
    state = make_state()
    state["context"] = {
        "symbol": "BTCUSDT",
        "price_summary": {"price": 65000.0, "change_24h_pct": 2.3,
                          "volume_24h": 28e9, "high_24h": 66000.0,
                          "low_24h": 64000.0, "ohlcv_24h": []},
        "news_items": [], "onchain_summary": {},
        "social_summary": {}, "data_gaps": [],
        "price_source": "binance", "news_source": "rss",
        "funding_rate_summary": funding_rate_summary,
    }
    state["analysis"] = {
        "sentiment_score": 0.1, "sentiment_label": "neutral",
        "sentiment_drivers": [],
        "market_structure": {
            "bias": "neutral", "rsi": 52.0, "ma_trend": "sideways",
            "confidence_score": 0.20, "explanation": "neutral",
            "swing_highs": [], "swing_lows": [], "liquidity_sweeps": [],
            "order_blocks": [], "bos_choch": [], "volume_confirmed": False,
            "invalidation_level": None, "macd_histogram_slope": 0.0,
            "momentum_pct": 0.0, "ml_probability_1r": None, "ml_probability_2r": None,
        },
        "risk_level": "low", "risk_factors": ["No significant risk factors detected"],
    }
    return state


async def test_funding_signal_in_key_signals_when_moderate():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": +0.00080, "funding_time": "", "source": "binance"}
    ))
    signals = result["report"]["key_signals"]
    assert any("Funding rate" in s for s in signals)


async def test_neutral_funding_not_in_key_signals():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": +0.00010, "funding_time": "", "source": "binance"}
    ))
    signals = result["report"]["key_signals"]
    assert not any("Funding rate" in s for s in signals)


async def test_funding_source_binance():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": 0.00010, "funding_time": "", "source": "binance"}
    ))
    assert result["report"]["funding_source"] == "binance"


async def test_funding_source_mock():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(
        {"rate": 0.00080, "funding_time": "", "source": "mock"}
    ))
    assert result["report"]["funding_source"] == "mock"


async def test_funding_source_unavailable_when_summary_is_none():
    node   = make_supervisor(_make_settings())
    result = await node(_state_with_context(None))
    assert result["report"]["funding_source"] == "unavailable"
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/unit/test_supervisor_funding.py -v
```
Expected: `KeyError: 'funding_source'` on all tests

- [ ] **Step 3: Update `agents/supervisor.py`**

In `_deterministic_supervisor`, add after the key_signals RSI line and before the report dict:

```python
# agents/supervisor.py  — inside _deterministic_supervisor

# (keep all existing code up to key_signals.append(f"RSI: {rsi:.0f}"))

    # Funding rate key signal
    funding = context.get("funding_rate_summary")
    if funding is not None and abs(funding["rate"]) >= 0.0005:
        direction = "longs" if funding["rate"] > 0 else "shorts"
        key_signals.append(f"Funding rate {funding['rate']:+.3%} ({direction} crowded)")

    # Funding source provenance
    funding_source = funding["source"] if funding is not None else "unavailable"

# (keep existing risk_warnings / risk_level / narrative sections unchanged)

# In report dict, add:
    report: IntelligenceReport = {
        ...
        "funding_source":   funding_source,
    }
```

Full updated `_deterministic_supervisor` function:

```python
def _deterministic_supervisor(state: AgentState) -> dict:
    analysis = state.get("analysis") or {}
    context  = state.get("context") or {}

    sentiment_score = analysis.get("sentiment_score") or 0.0
    sentiment_label = analysis.get("sentiment_label") or "neutral"
    ms              = analysis.get("market_structure") or {}
    risk_level      = analysis.get("risk_level") or "medium"
    risk_factors    = list(analysis.get("risk_factors") or [])
    data_gaps       = list(context.get("data_gaps") or [])

    rsi           = ms.get("rsi", 50.0)
    ma_trend      = ms.get("ma_trend", "sideways")
    momentum      = ms.get("momentum_pct", 0.0)
    ms_bias       = ms.get("bias", "neutral")
    ms_confidence = ms.get("confidence_score", 0.0)

    # 1. Vote-based bias
    bull, bear = 0, 0
    if ms_bias == "bullish":    bull += 2
    elif ms_bias == "bearish":  bear += 2
    if sentiment_score > 0.1:   bull += 1
    elif sentiment_score < -0.1: bear += 1
    if ma_trend == "uptrend":   bull += 1
    elif ma_trend == "downtrend": bear += 1
    if rsi > 55:  bull += 1
    elif rsi < 45: bear += 1
    if momentum > 1.0:  bull += 1
    elif momentum < -1.0: bear += 1

    market_bias = "bullish" if bull > bear else "bearish" if bear > bull else "neutral"

    # 2. Confidence score
    total       = bull + bear
    signal_conf = (max(bull, bear) / total * 0.4) if total > 0 else 0.0
    base_conf   = 0.20 + signal_conf + ms_confidence * 0.25
    gap_penalty = 0.05 * len(data_gaps)
    confidence  = round(max(0.10, min(1.0, base_conf - gap_penalty)), 2)

    # 3. Key signals
    price_summary = context.get("price_summary", {})
    coin   = state["symbol"].replace("USDT", "")
    change = price_summary.get("change_24h_pct", 0.0)

    key_signals: list[str] = []
    if change is not None:
        key_signals.append(f"{coin} {'+' if change >= 0 else ''}{change:.2f}% in 24h")
    if ms.get("bos_choch"):
        last_event = ms["bos_choch"][-1]
        key_signals.append(
            f"{last_event['type']} {last_event['direction']} "
            f"@ {last_event['break_level']:.2f}"
        )
    if ms_confidence > 0:
        key_signals.append(f"Market structure: {ms_bias} ({ms_confidence:.0%} confidence)")
    if ma_trend in ("uptrend", "downtrend"):
        key_signals.append(f"MA trend: {ma_trend}")
    key_signals.append(f"RSI: {rsi:.0f}")
    drivers = analysis.get("sentiment_drivers") or []
    key_signals.extend(drivers[:1])

    # Funding rate key signal
    funding = context.get("funding_rate_summary")
    if funding is not None and abs(funding["rate"]) >= 0.0005:
        direction = "longs" if funding["rate"] > 0 else "shorts"
        key_signals.append(f"Funding rate {funding['rate']:+.3%} ({direction} crowded)")

    # Funding source provenance
    funding_source = funding["source"] if funding is not None else "unavailable"

    # 4. Risk warnings
    risk_warnings: list[str] = [
        f for f in risk_factors
        if f != "No significant risk factors detected"
    ][:3]
    if rsi >= 70:
        risk_warnings.append("RSI overbought — pullback risk elevated")
    elif rsi <= 30:
        risk_warnings.append("RSI oversold — reversal risk elevated")
    if not risk_warnings:
        risk_warnings = ["No significant risk factors detected"]

    # 5. Risk level
    if rsi >= 75 and market_bias == "bullish":
        if risk_level == "low":
            risk_level = "medium"
    if any(w not in _TRIVIAL_WARNINGS for w in risk_warnings):
        if risk_level == "low":
            risk_level = "medium"

    # 6. Narrative
    rsi_note = ""
    if rsi >= 70:     rsi_note = ", pullback risk"
    elif rsi <= 30:   rsi_note = ", reversal risk"

    narrative = (
        f"{coin} shows {market_bias} bias. "
        f"Market structure: {ms_bias} ({ms_confidence:.0%}). "
        f"RSI {rsi:.0f}{rsi_note}, MA {ma_trend}, sentiment {sentiment_label}. "
        f"Risk: {risk_level}."
    )
    if data_gaps:
        narrative += f" Limited data: {', '.join(data_gaps)}."

    report: IntelligenceReport = {
        "run_id":           state["run_id"],
        "symbol":           state["symbol"],
        "requested_at":     state["requested_at"],
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "market_bias":      market_bias,
        "confidence_score": confidence,
        "key_signals":      key_signals[:5] or ["Insufficient signal data"],
        "risk_warnings":    risk_warnings[:5],
        "narrative":        narrative,
        "data_gaps":        data_gaps,
        "error":            None,
        "llm_used":         False,
        "market_structure": ms if ms.get("bias") else None,
        "price_source":     context.get("price_source", "unknown"),
        "news_source":      context.get("news_source", "unknown"),
        "analysis_engine":  "rule-based",
        "funding_source":   funding_source,
    }
    return {"report": report}
```

- [ ] **Step 4: Run supervisor tests**

```
uv run pytest tests/unit/test_supervisor_funding.py tests/unit/test_supervisor.py -v
```
Expected: all PASSED (both new and existing supervisor tests)

- [ ] **Step 5: Commit**

```
git add agents/supervisor.py tests/unit/test_supervisor_funding.py
git commit -m "feat: add funding rate key_signal and funding_source to supervisor report"
```

---

## Task 9: API schema + Telegram footer

**Files:**
- Modify: `api/schemas.py`
- Modify: `publishers/telegram_publisher.py`
- Modify: `tests/integration/test_api.py`

- [ ] **Step 1: Update `api/schemas.py` — add `funding_source`**

```python
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
```

- [ ] **Step 2: Update `publishers/telegram_publisher.py` — footer**

Replace the footer lines in `format_intelligence_report`:

```python
    # Footer — provenance
    llm_used     = report.get("llm_used", False)
    engine_label = "Claude AI" if llm_used else "rule-based"
    price_src    = report.get("price_source", "unknown")
    news_src     = report.get("news_source", "unknown")
    funding_src  = report.get("funding_source", "unavailable")
    lines += [
        "",
        f"<i>Engine: {engine_label}  |  Price: {price_src}  |  "
        f"News: {news_src}  |  Funding: {funding_src}</i>",
    ]
```

- [ ] **Step 3: Update `tests/integration/test_api.py`**

In `test_report_schema_matches_expected_fields`, add `"funding_source"` to the `required` set:

```python
    required = {
        "run_id", "symbol", "requested_at", "generated_at",
        "market_bias", "confidence_score", "key_signals",
        "risk_warnings", "narrative", "data_gaps", "llm_used",
        "price_source", "news_source", "analysis_engine", "funding_source",
    }
```

Append a new test at the end of the file:

```python
def test_report_response_includes_funding_source(client):
    resp = client.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 200
    body = resp.json()
    assert "funding_source" in body
    assert isinstance(body["funding_source"], str)
    assert body["funding_source"] in ("binance", "mock", "unavailable", "unknown")
```

- [ ] **Step 4: Run API tests**

```
uv run pytest tests/integration/test_api.py -v
```
Expected: all PASSED including new test

- [ ] **Step 5: Commit**

```
git add api/schemas.py publishers/telegram_publisher.py tests/integration/test_api.py
git commit -m "feat: add funding_source to API schema and Telegram footer"
```

---

## Task 10: Full verification + push

- [ ] **Step 1: Run the complete test suite**

```
uv run pytest tests/ -v
```
Expected: all tests PASS. Count should be previous count + ~25 new tests.

- [ ] **Step 2: If any test fails, diagnose and fix before continuing**

Common failure points:
- `test_pipeline_mock_includes_funding_source` — check supervisor added `funding_source` to report
- `test_pipeline_mock_btcusdt_funding_signal` — check mock rate is 0.00080 (≥ 0.0005 threshold), check supervisor adds key_signal
- `test_report_schema_matches_expected_fields` — check `funding_source` in `IntelligenceReportResponse`
- Any existing supervisor test — check `_state_with_full_analysis` context dict; `funding_rate_summary` key absence is fine (`.get()` returns None → `funding_source = "unavailable"`)

- [ ] **Step 3: Push**

```
git push
```

- [ ] **Step 4: Confirm test count in output**

Final line should show something like: `XX passed in X.XXs` with no failures.

---

## Self-Review Checklist

| Spec requirement | Task |
|---|---|
| `BinanceFundingRateAdapter` — parse fundingRate string, fundingTime ms→ISO UTC | Task 2 |
| `BinanceFundingRateAdapter` — empty list → None, 404 → None, other errors → raise | Task 2 |
| `MockFundingRateAdapter` — BTCUSDT/ETHUSDT/default values | Task 1 |
| `FallbackAdapter` catches Binance failure, falls back to mock | Task 2 |
| `FundingRateSummary` TypedDict in state.py | Task 3 |
| `funding_rate_data: Optional[dict]` in `AgentState` | Task 3 |
| `funding_rate_summary: Optional[FundingRateSummary]` in `NormalizedMarketContext` | Task 3 |
| `funding_source: str` in `IntelligenceReport` | Task 3 |
| `make_state()` includes `funding_rate_data: None` | Task 3 |
| `make_funding_rate_collector` — try/except, returns data_gaps on failure | Task 4 |
| `aggregate_raw` — extracts `funding_rate_summary`, adds `funding_unavailable` to gaps | Task 5 |
| Factory routing — MOCK_MODE/dev/prod | Task 6 |
| `build_graph` — 5th param, 5th node, 4→5 barrier join | Task 6 |
| `_make_initial_state` in API route — `funding_rate_data: None` | Task 6 |
| `test_pipeline.py` — fixtures updated | Task 6 |
| Risk analyzer — two-level thresholds (≥ 0.0005 moderate, ≥ 0.0015 extreme) | Task 7 |
| Risk analyzer — inclusive thresholds (boundary tests) | Task 7 |
| Risk analyzer — `funding is None` → no error, no signal | Task 7 |
| Supervisor — funding key_signal when `abs(rate) >= 0.0005` | Task 8 |
| Supervisor — `funding_source` from summary or `"unavailable"` | Task 8 |
| API schema — `funding_source: str = "unavailable"` | Task 9 |
| Telegram footer — `| Funding: {funding_source}` | Task 9 |
| Aggregator tests (2) | Task 5 |
| Collector safety tests (3) | Task 4 |
| Adapter tests (8) | Tasks 1-2 |
| Risk analyzer tests (10, including boundary) | Task 7 |
| Supervisor funding tests (5) | Task 8 |
| Pipeline integration tests (2 new) | Task 6 |
| API schema test (1 new) | Task 9 |
