from config.settings import Settings


def test_defaults_are_cost_safe():
    s = Settings()
    assert s.ENV == "development"
    assert s.MOCK_MODE is True
    assert s.LLM_ENABLED is False
    assert s.DAILY_LLM_BUDGET_IDR == 0.0
    assert s.MAX_LLM_CALLS_PER_DAY == 0
    assert s.SCHEDULER_ENABLED is False
    assert s.SCHEDULER_INTERVAL_HOURS == 4
    assert s.ML_ENABLED is False
    assert s.MONTE_CARLO_ENABLED is False


def test_use_mock_returns_true_in_development():
    assert Settings(ENV="development").use_mock() is True


def test_use_mock_returns_true_in_test():
    assert Settings(ENV="test").use_mock() is True


def test_use_mock_returns_false_in_production_without_flag():
    assert Settings(ENV="production", MOCK_MODE=False).use_mock() is False


def test_use_mock_returns_true_in_production_with_mock_flag():
    assert Settings(ENV="production", MOCK_MODE=True).use_mock() is True


def test_scheduler_interval_hours_default():
    s = Settings()
    assert s.SCHEDULER_INTERVAL_HOURS == 4
