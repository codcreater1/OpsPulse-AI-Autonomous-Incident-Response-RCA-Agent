"""LangGraph StateGraph with conditional routing and the self-correction loop (Developer 1)."""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.agent.nodes import (
    analyze_cause_node,
    decide_next,
    evaluate_quality_node,
    github_fetch_node,
    neon_lookup_node,
    parse_log_node,
)
from src.agent.state import IncidentState


def should_continue(state: IncidentState) -> Literal["analyze_cause", "finalize"]:
    """Loop back to the RCA node while confidence < threshold and iterations < max; else finish."""
    route = decide_next(state["confidence_score"], state["iterations"], state.get("code_context"))
    return "analyze_cause" if route == "RETRY" else "finalize"


def build_graph() -> StateGraph:
    graph = StateGraph(IncidentState)
    graph.add_node("parse_log", parse_log_node)
    graph.add_node("github_fetch", github_fetch_node)
    graph.add_node("neon_lookup", neon_lookup_node)
    graph.add_node("analyze_cause", analyze_cause_node)
    graph.add_node("evaluate_quality", evaluate_quality_node)

    graph.add_edge(START, "parse_log")
    graph.add_edge("parse_log", "github_fetch")
    graph.add_edge("github_fetch", "neon_lookup")
    graph.add_edge("neon_lookup", "analyze_cause")
    graph.add_edge("analyze_cause", "evaluate_quality")
    graph.add_conditional_edges(
        "evaluate_quality",
        should_continue,
        {"analyze_cause": "analyze_cause", "finalize": END},
    )
    return graph


ops_pulse_graph = build_graph().compile()
