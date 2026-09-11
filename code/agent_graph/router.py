"""Routing logic for the Homework 2 Part 3 stateful agent graph."""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END

from .state import AgentState


def router_logic(state: AgentState) -> Literal["planner", "reviewer", "__end__"]:
    ceiling = state.get("turn_ceiling", 10)
    turn_count = state.get("turn_count", 0)

    if not state.get("planner_proposal"):
        if turn_count >= ceiling:
            return END
        return "planner"

    feedback = state.get("reviewer_feedback")
    if feedback is None:
        return "reviewer"

    if feedback.get("has_issues"):
        if turn_count >= ceiling:
            return END
        return "planner"

    return END