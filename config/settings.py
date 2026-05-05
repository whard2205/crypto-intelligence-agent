from __future__ import annotations
from typing import Literal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: Literal["development", "test", "production"] = "development"
    MOCK_MODE: bool = True
    LLM_ENABLED: bool = False
    DAILY_LLM_BUDGET_IDR: float = 0.0
    MAX_LLM_CALLS_PER_DAY: int = 0
    SCHEDULER_ENABLED: bool = False
    ML_ENABLED: bool = False
    MONTE_CARLO_ENABLED: bool = False

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_SUPERVISOR_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_ANALYZER_MODEL: str = "claude-haiku-4-5-20251001"

    ETHERSCAN_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    API_AUTH_ENABLED: bool = False
    API_KEY: str = ""

    DB_PATH: str = "data/report_history.db"

    DISPLAY_TIMEZONE: str = "Asia/Jakarta"
    WATCH_SYMBOLS: str = "BTCUSDT,ETHUSDT"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def use_mock(self) -> bool:
        return self.ENV in ("development", "test") or self.MOCK_MODE


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
