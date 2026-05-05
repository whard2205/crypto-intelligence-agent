import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.deps import get_repo
from config.settings import Settings, get_settings


# ---------------------------------------------------------------------------
# No-op repo — prevents test runs from writing to the real DB
# ---------------------------------------------------------------------------

class _NoopRepo:
    async def init_db(self): pass
    async def save(self, report): pass
    async def get_latest(self, symbol, limit=10): return []
    async def prune(self, symbol, keep=100): pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    """Ensure each test starts with a clean dependency override map."""
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    app.dependency_overrides[get_repo] = lambda: _NoopRepo()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client():
    def _override():
        return Settings(
            ENV="test", MOCK_MODE=True, LLM_ENABLED=False,
            API_AUTH_ENABLED=True, API_KEY="test-secret",
        )
    app.dependency_overrides[get_settings] = _override
    app.dependency_overrides[get_repo]     = lambda: _NoopRepo()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert "mock_mode" in body
    assert "llm_enabled" in body


# ---------------------------------------------------------------------------
# Report — success path
# ---------------------------------------------------------------------------

def test_report_endpoint_success(client):
    resp = client.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["market_bias"] in ("bullish", "bearish", "neutral")
    assert 0.0 <= body["confidence_score"] <= 1.0
    assert isinstance(body["key_signals"], list)
    assert isinstance(body["narrative"], str)
    assert body["llm_used"] is False


def test_report_schema_matches_expected_fields(client):
    resp = client.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 200
    body = resp.json()

    required = {
        "run_id", "symbol", "requested_at", "generated_at",
        "market_bias", "confidence_score", "key_signals",
        "risk_warnings", "narrative", "data_gaps", "llm_used",
        "price_source", "news_source", "analysis_engine",
    }
    assert required.issubset(body.keys()), f"Missing keys: {required - body.keys()}"
    assert isinstance(body["data_gaps"], list)
    assert isinstance(body["risk_warnings"], list)
    assert isinstance(body["generated_at"], str)
    # market_structure should be present (dict or null)
    assert "market_structure" in body
    assert body["analysis_engine"] == "rule-based"
    assert body["llm_used"] is False


# ---------------------------------------------------------------------------
# Report — invalid symbol
# ---------------------------------------------------------------------------

def test_report_invalid_symbol(client):
    # lowercase letters fail the ^[A-Z][A-Z0-9]{2,19}$ pattern → 422
    resp = client.get("/report?symbol=btcusdt")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth — disabled by default
# ---------------------------------------------------------------------------

def test_api_auth_disabled_by_default(client):
    # Default settings have API_AUTH_ENABLED=False — no key needed
    resp = client.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Auth — enabled, key required
# ---------------------------------------------------------------------------

def test_api_auth_enabled_requires_key(auth_client):
    # No key → 401
    resp = auth_client.get("/report?symbol=BTCUSDT")
    assert resp.status_code == 401

    # Wrong key → 401
    resp = auth_client.get("/report?symbol=BTCUSDT", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401

    # Correct key → 200
    resp = auth_client.get("/report?symbol=BTCUSDT", headers={"X-API-Key": "test-secret"})
    assert resp.status_code == 200
