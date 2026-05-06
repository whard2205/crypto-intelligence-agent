# graph/pipeline.py
from __future__ import annotations
from langgraph.graph import StateGraph, START, END

from config.settings import Settings
from data_sources.base import DataSourceAdapter
from graph.state import AgentState
from graph.aggregator import aggregate_raw, fan_out_analyzers, merge_analysis
from graph.edges import route_after_aggregate


def build_graph(
    settings:             Settings,
    price_adapter:        DataSourceAdapter,
    news_adapter:         DataSourceAdapter,
    onchain_adapter:      DataSourceAdapter,
    social_adapter:       DataSourceAdapter,
    funding_rate_adapter: DataSourceAdapter,
):
    """Assemble and compile the LangGraph StateGraph."""
    from agents.collectors.price_collector         import make_price_collector
    from agents.collectors.news_collector          import make_news_collector
    from agents.collectors.onchain_collector       import make_onchain_collector
    from agents.collectors.social_collector        import make_social_collector
    from agents.collectors.funding_rate_collector  import make_funding_rate_collector
    from agents.analyzers.sentiment_analyzer       import make_sentiment_analyzer
    from agents.analyzers.market_structure_analyzer import make_market_structure_analyzer
    from agents.analyzers.risk_analyzer            import make_risk_analyzer
    from agents.supervisor                         import make_supervisor

    workflow = StateGraph(AgentState)

    # --- Nodes ---
    workflow.add_node("collect_price",         make_price_collector(price_adapter))
    workflow.add_node("collect_news",          make_news_collector(news_adapter))
    workflow.add_node("collect_onchain",       make_onchain_collector(onchain_adapter))
    workflow.add_node("collect_social",        make_social_collector(social_adapter))
    workflow.add_node("collect_funding_rate",  make_funding_rate_collector(funding_rate_adapter))
    workflow.add_node("aggregate_raw",         aggregate_raw)
    workflow.add_node("fan_out_analyzers",     fan_out_analyzers)
    workflow.add_node("analyze_sentiment",         make_sentiment_analyzer(settings))
    workflow.add_node("analyze_market_structure",  make_market_structure_analyzer(settings))
    workflow.add_node("analyze_risk",              make_risk_analyzer(settings))
    workflow.add_node("merge_analysis",  merge_analysis)
    workflow.add_node("supervisor",      make_supervisor(settings))
    workflow.add_node("error_exit",      lambda state: {})

    # --- Edges ---
    workflow.add_edge(START, "collect_price")
    workflow.add_edge(START, "collect_news")
    workflow.add_edge(START, "collect_onchain")
    workflow.add_edge(START, "collect_social")
    workflow.add_edge(START, "collect_funding_rate")

    # Barrier join: all 5 collectors → aggregate_raw
    workflow.add_edge(
        ["collect_price", "collect_news", "collect_onchain",
         "collect_social", "collect_funding_rate"],
        "aggregate_raw",
    )

    workflow.add_conditional_edges(
        "aggregate_raw",
        route_after_aggregate,
        {"error_exit": "error_exit", "fan_out_analyzers": "fan_out_analyzers"},
    )

    workflow.add_edge("fan_out_analyzers", "analyze_sentiment")
    workflow.add_edge("fan_out_analyzers", "analyze_market_structure")
    workflow.add_edge("fan_out_analyzers", "analyze_risk")

    workflow.add_edge(
        ["analyze_sentiment", "analyze_market_structure", "analyze_risk"],
        "merge_analysis",
    )

    workflow.add_edge("merge_analysis", "supervisor")
    workflow.add_edge("supervisor", END)
    workflow.add_edge("error_exit", END)

    return workflow.compile()


def build_pipeline(settings: Settings):
    """Convenience wrapper: wire mock adapters."""
    from data_sources.mock.mock_price        import MockPriceAdapter
    from data_sources.mock.mock_news         import MockNewsAdapter
    from data_sources.mock.mock_onchain      import MockOnChainAdapter
    from data_sources.mock.mock_social       import MockSocialAdapter
    from data_sources.mock.mock_funding_rate import MockFundingRateAdapter

    return build_graph(
        settings,
        price_adapter=        MockPriceAdapter(),
        news_adapter=         MockNewsAdapter(),
        onchain_adapter=      MockOnChainAdapter(),
        social_adapter=       MockSocialAdapter(),
        funding_rate_adapter= MockFundingRateAdapter(),
    )
