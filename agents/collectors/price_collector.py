from __future__ import annotations
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_price_collector(adapter: DataSourceAdapter):
    async def collect_price(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if result is None:
            return {"data_gaps": ["price_unavailable"]}
        return {"price_data": result}
    return collect_price
