"""Assembles the Planner/Reviewer/Supervisor stateful graph (Homework 2, Part 3)."""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import planner_node, reviewer_node, supervisor_node
from .router import router_logic


def build_workflow(*, planner_fn=None, reviewer_fn=None):
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_fn or planner_node)
    graph.add_node("reviewer", reviewer_fn or reviewer_node)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "reviewer": "reviewer", END: END},
    )
    graph.add_edge("planner", "supervisor")
    graph.add_edge("reviewer", "supervisor")

    return graph.compile()