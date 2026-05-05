from __future__ import annotations
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_onchain_collector(adapter: DataSourceAdapter):
    async def collect_onchain(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if result is None:
            return {"data_gaps": ["onchain_unavailable"]}
        return {"onchain_data": result}
    return collect_onchain
