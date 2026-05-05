from __future__ import annotations
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_social_collector(adapter: DataSourceAdapter):
    async def collect_social(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if result is None:
            return {"data_gaps": ["social_unavailable"]}
        return {"social_data": result}
    return collect_social
