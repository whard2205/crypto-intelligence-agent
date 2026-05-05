import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.deps import get_repo, get_settings
from config.settings import Settings


# ---------------------------------------------------------------------------
# Fake repo — no real DB needed for API-layer tests
# ---------------------------------------------------------------------------

class _FakeRepo:
    def __init__(self, seed: list | None = None):
        self._data: list[dict] = list(seed or [])

    async def init_db(self): pass

    async def save(self, report: dict):
        self._data.append(report)

    async def get_latest(self, symbol: str, limit: int = 10) -> list[dict]:
        return [r for r in self._data if r.get("symbol") == symbol][:limit]

    async def prune(self, symbol: str, keep: int = 100): pass


def _sample_report(symbol: str = "BTCUSDT") -> dict:
    return {
        "run_id": "r1", "symbol": symbol,
        "requested_at": "2026-05-04T02:00:00+00:00",
        "generated_at": "2026-05-04T02:00:01+00:00",
        "market_bias": "bullish", "confidence_score": 0.80,
        "key_signals": ["BTC +2%"], "risk_warnings": [], "narrative": "ok",
        "data_gaps": [], "error": None, "llm_used": False, "market_structure": None,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_repo():
    return _FakeRepo()


@pytest.fixture
def client(fake_repo):
    app.dependency_overrides[get_repo] = lambda: fake_repo
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# /history tests
# ---------------------------------------------------------------------------

def test_history_endpoint_empty(client):
    resp = client.get("/history?symbol=BTCUSDT&limit=10")
    assert resp.status_code == 200
    assert resp.json() == []


def test_history_endpoint_returns_saved_reports(fake_repo, client):
    # Pre-seed the fake repo directly (save() just appends to _data)
    fake_repo._data.append(_sample_report("BTCUSDT"))
    resp = client.get("/history?symbol=BTCUSDT&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "BTCUSDT"


def test_history_invalid_symbol(client):
    resp = client.get("/history?symbol=btcusdt")   # lowercase → 422
    assert resp.status_code == 422


def test_history_limit_capped_at_100(client):
    resp = client.get("/history?symbol=BTCUSDT&limit=101")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /report → saves to repo
# ---------------------------------------------------------------------------

def test_report_saves_to_history(fake_repo):
    app.dependency_overrides[get_repo] = lambda: fake_repo
    with TestClient(app) as c:
        resp = c.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 200
    assert len(fake_repo._data) == 1
    assert fake_repo._data[0]["symbol"] == "BTCUSDT"
    assert fake_repo._data[0]["error"] is None
