import pytest
from storage.report_history import ReportHistoryRepository


def _make_report(symbol: str = "BTCUSDT", run_id: str = "run-0", ts: str = "2026-05-04T02:00:00+00:00", **extra) -> dict:
    return {
        "run_id":           run_id,
        "symbol":           symbol,
        "requested_at":     ts,
        "generated_at":     ts,
        "market_bias":      "bullish",
        "confidence_score": 0.80,
        "key_signals":      ["BTC +2.3%"],
        "risk_warnings":    [],
        "narrative":        "Test.",
        "data_gaps":        [],
        "error":            None,
        "llm_used":         False,
        "market_structure": None,
        **extra,
    }


# ---------------------------------------------------------------------------
# 1. Save and retrieve
# ---------------------------------------------------------------------------

async def test_save_and_retrieve(tmp_path):
    repo = ReportHistoryRepository(str(tmp_path / "test.db"))
    await repo.init_db()
    await repo.save(_make_report())
    results = await repo.get_latest("BTCUSDT", limit=10)
    assert len(results) == 1
    assert results[0]["symbol"] == "BTCUSDT"
    assert results[0]["market_bias"] == "bullish"


# ---------------------------------------------------------------------------
# 2. Most-recent-first ordering
# ---------------------------------------------------------------------------

async def test_get_latest_returns_most_recent_first(tmp_path):
    repo = ReportHistoryRepository(str(tmp_path / "test.db"))
    await repo.init_db()
    for i in range(3):
        r = _make_report(run_id=f"run-{i}", ts=f"2026-05-04T02:00:0{i}+00:00")
        r["confidence_score"] = 0.5 + i * 0.1
        await repo.save(r)
    results = await repo.get_latest("BTCUSDT", limit=10)
    # Most recent first → confidence 0.7, then 0.6, then 0.5
    assert results[0]["confidence_score"] == pytest.approx(0.7)
    assert results[-1]["confidence_score"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 3. Symbol isolation
# ---------------------------------------------------------------------------

async def test_get_latest_filters_by_symbol(tmp_path):
    repo = ReportHistoryRepository(str(tmp_path / "test.db"))
    await repo.init_db()
    await repo.save(_make_report(symbol="BTCUSDT", run_id="btc"))
    await repo.save(_make_report(symbol="ETHUSDT", run_id="eth"))
    btc = await repo.get_latest("BTCUSDT")
    eth = await repo.get_latest("ETHUSDT")
    assert len(btc) == 1 and btc[0]["symbol"] == "BTCUSDT"
    assert len(eth) == 1 and eth[0]["symbol"] == "ETHUSDT"


# ---------------------------------------------------------------------------
# 4. Explicit prune
# ---------------------------------------------------------------------------

async def test_prune_keeps_only_n_rows(tmp_path):
    repo = ReportHistoryRepository(str(tmp_path / "test.db"))
    await repo.init_db()
    for i in range(5):
        r = _make_report(run_id=f"run-{i}", ts=f"2026-05-04T02:00:0{i}+00:00")
        await repo.save(r)
    rows_before = await repo.get_latest("BTCUSDT", limit=100)
    assert len(rows_before) == 5
    await repo.prune("BTCUSDT", keep=3)
    rows_after = await repo.get_latest("BTCUSDT", limit=100)
    assert len(rows_after) == 3


# ---------------------------------------------------------------------------
# 5. Auto-prune on save (keep=100 default)
# ---------------------------------------------------------------------------

async def test_auto_prune_caps_at_100(tmp_path):
    repo = ReportHistoryRepository(str(tmp_path / "test.db"))
    await repo.init_db()
    for i in range(105):
        r = _make_report(
            run_id=f"run-{i:03d}",
            ts=f"2026-05-04T{i // 60:02d}:{i % 60:02d}:00+00:00",
        )
        await repo.save(r)
    results = await repo.get_latest("BTCUSDT", limit=200)
    assert len(results) <= 100
