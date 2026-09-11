"""Planner, Reviewer, and Supervisor nodes for the Part 3 stateful agent graph."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field, ValidationError, field_validator

from .state import AgentState


class PlannerOutput(BaseModel):
    """Schema enforced on every Planner attempt (Homework 2, Part 4)."""
    tags: List[str] = Field(..., min_length=3, max_length=3)
    summary: str

    @field_validator("tags")
    @classmethod
    def check_tag_lengths(cls, value: List[str]) -> List[str]:
        for tag in value:
            if not (3 <= len(tag) <= 30):
                raise ValueError(f"tag {tag!r} must be 3-30 characters long")
        return value

    @field_validator("summary")
    @classmethod
    def check_summary_length(cls, value: str) -> str:
        if len(value.split()) > 25:
            raise ValueError("summary must be at most 25 words")
        return value


def _parse_json_object(text: str) -> Dict[str, Any]:
    """Parse a JSON object, tolerating an accidental Markdown fence."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            value = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


PLANNER_SCHEMA_HINT = (
    '{"tags": ["tag1", "tag2", "tag3"], "summary": "..."} '
    "-- exactly three tags, each 3-30 characters, and a summary of at most 25 words."
)


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Generate (or regenerate) a tags+summary proposal, validated against PlannerOutput."""
    print("---NODE: Planner---")
    client = state["llm"]

    retry_note = ""
    if state.get("validation_error"):
        retry_note = (
            f"\nYour previous attempt failed schema validation with this error: "
            f"{state['validation_error']}\nFix it and return only valid JSON."
        )
    elif state.get("reviewer_feedback") and state["reviewer_feedback"].get("has_issues"):
        retry_note = (
            f"\nThe Reviewer rejected your previous attempt: "
            f"{state['reviewer_feedback'].get('explanation', '')}\nRevise accordingly."
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are Planner. Derive exactly three specific topical tags and one concise "
                "summary from only the supplied title and content. Never use fixed domain "
                "keywords. The summary must be one sentence with at most 25 words. Return only "
                f"JSON matching this shape: {PLANNER_SCHEMA_HINT}{retry_note}"
            ),
        },
        {
            "role": "user",
            "content": f"Title: {state['title']}\nContent: {state['content']}",
        },
    ]

    response = client.complete(messages, temperature=0.0 if state.get("strict") else 0.7)
    payload = _parse_json_object(response.content)

    try:
        validated = PlannerOutput(**payload)
    except ValidationError as exc:
        print(f"---Planner output failed schema validation: {exc}---")
        return {
            "planner_proposal": None,
            "validation_error": str(exc),
            "reviewer_feedback": None,
        }

    return {
        "planner_proposal": validated.model_dump(),
        "validation_error": None,
        "reviewer_feedback": None,
    }


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    """Check the current planner_proposal for grounding, uniqueness, and relevance."""
    print("---NODE: Reviewer---")
    client = state["llm"]
    proposal = state["planner_proposal"]

    messages = [
        {
            "role": "system",
            "content": (
                "You are Reviewer. Check that all three tags are distinct, specific, and "
                "supported by the supplied title/content, and that the summary is accurate and "
                "at most 25 words. Return only JSON: "
                '{"has_issues": <true/false>, "explanation": "..."}'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Title: {state['title']}\nContent: {state['content']}\n"
                f"Planner proposal: {json.dumps(proposal, ensure_ascii=False)}"
            ),
        },
    ]

    response = client.complete(messages, temperature=0.0)
    feedback = _parse_json_object(response.content)
    if "has_issues" not in feedback:
        feedback = {"has_issues": False, "explanation": "Reviewer response unparsable; accepting proposal."}

    print(f"---Reviewer feedback: {feedback}---")
    return {"reviewer_feedback": feedback}


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """The only job of this node is to advance the turn counter."""
    return {"turn_count": state.get("turn_count", 0) + 1}