from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DataSourceAdapter(ABC):
    source_name: str = "unknown"

    @abstractmethod
    async def fetch(self, symbol: str) -> Optional[Any]: ...


class FallbackAdapter(DataSourceAdapter):
    """Try each adapter in order; return the first non-None result.

    Production rule: mock adapters must never be silently used in production
    unless MOCK_MODE=true. The factory enforces this — FallbackAdapter itself
    has no concept of environment.
    """

    def __init__(self, chain: list[DataSourceAdapter]) -> None:
        self._chain = chain
        self.source_name = "fallback(" + ",".join(a.source_name for a in chain) + ")"

    async def fetch(self, symbol: str) -> Optional[Any]:
        for adapter in self._chain:
            try:
                result = await adapter.fetch(symbol)
                if result is not None:
                    return result
                logger.warning("[%s] returned None for symbol=%s", adapter.source_name, symbol)
            except Exception as exc:
                logger.warning("[%s] failed for symbol=%s: %s", adapter.source_name, symbol, exc)
        logger.error("All adapters exhausted for symbol=%s via %s", symbol, self.source_name)
        return None
