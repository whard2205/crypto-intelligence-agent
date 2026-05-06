from __future__ import annotations
import logging
from data_sources.base import DataSourceAdapter
from graph.state import AgentState

logger = logging.getLogger(__name__)


def make_funding_rate_collector(adapter: DataSourceAdapter):
    async def collect_funding_rate(state: AgentState) -> dict:
        try:
            result = await adapter.fetch(state["symbol"])
            if result is None:
                return {"data_gaps": ["funding_unavailable"]}
            return {"funding_rate_data": result}
        except Exception as exc:
            logger.warning("funding_rate fetch failed for %s: %s", state["symbol"], exc)
            return {"data_gaps": ["funding_unavailable"]}
    return collect_funding_rate
