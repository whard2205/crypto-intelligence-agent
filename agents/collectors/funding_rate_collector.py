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
