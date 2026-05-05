from graph.state import AgentState


def route_after_aggregate(state: AgentState) -> str:
    """Route to error_exit when aggregate_raw set an ErrorReport; else fan_out_analyzers."""
    if state.get("report") is not None:
        return "error_exit"
    return "fan_out_analyzers"
