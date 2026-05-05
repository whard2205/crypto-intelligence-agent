from __future__ import annotations
from data_sources.base import DataSourceAdapter
from graph.state import AgentState


def make_news_collector(adapter: DataSourceAdapter):
    async def collect_news(state: AgentState) -> dict:
        result = await adapter.fetch(state["symbol"])
        if not result:
            return {"data_gaps": ["news_unavailable"]}
        return {"news_data": result}   # operator.add reducer appends to list
    return collect_news
