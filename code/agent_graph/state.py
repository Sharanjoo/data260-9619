"""Shared state for the Homework 2 Part 3 stateful agent graph."""
from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # Fields specified in the assignment:
    title: str
    content: str
    email: str
    strict: bool
    task: str
    llm: Any
    planner_proposal: Optional[Dict[str, Any]]
    reviewer_feedback: Optional[Dict[str, Any]]
    turn_count: int
    # Extensions required by Part 4 (turn-ceiling experiments, validation retries):
    turn_ceiling: int
    validation_error: Optional[str]


def initialize_state(
    title: str,
    content: str,
    email: str,
    llm: Any,
    *,
    task: str = "grocery_recall_tagging",
    strict: bool = False,
    turn_ceiling: int = 10,
) -> AgentState:
    return AgentState(
        title=title,
        content=content,
        email=email,
        strict=strict,
        task=task,
        llm=llm,
        planner_proposal=None,
        reviewer_feedback=None,
        turn_count=0,
        turn_ceiling=turn_ceiling,
        validation_error=None,
    )