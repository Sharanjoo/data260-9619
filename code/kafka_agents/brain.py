"""HW8 Part 2 - what each agent 'thinks with': qwen3:8b through the HW1 Ollama adapter (llm mode) or a fixed
deterministic text (fast mode, used only for the Part 3 failure tests so they run in seconds)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, List, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))  # appended, not inserted: the repo's own `code/` package must not shadow the stdlib

STEPS_FAST = [
    "Identify the recalled product and why it was recalled",
    "Tell the shopper what to do with product they already have",
    "Point to the official recall notice for refund and contact details",
]
DRAFT_FAST = ("Do not eat or serve the recalled product. Return it to the store or throw it away, wash hands and "
              "any surfaces it touched, and follow the official recall notice for refund and contact details. "
              "See a doctor if you feel unwell after eating it.")

URL_OR_PHONE = re.compile(r"https?://|www\.|\b\d{3}[-.\s]\d{3,4}[-.\s]\d{4}\b")


def _json(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model reply is not JSON") from None
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("model reply is not a JSON object")
    return data


class Brain:
    def __init__(self, mode: str = "llm") -> None:
        if mode not in ("llm", "fast"):
            raise ValueError(f"HW8_AGENT_MODE must be llm or fast, not {mode!r}")
        self.mode = mode
        self.client = None
        self.calls = 0

    def _client(self) -> Any:
        if self.client is None:
            from src.model_client import OllamaModelClient  # the HW1 adapter
            self.client = OllamaModelClient(model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
                                            base_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
        return self.client

    async def _ask(self, system: str, user: str, as_json: bool) -> str:
        self.calls += 1
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        reply = await asyncio.to_thread(self._client().complete, messages,
                                        response_format="json" if as_json else None)
        return reply.content.strip()

    async def plan(self, question: str) -> List[str]:
        if self.mode == "fast":
            return list(STEPS_FAST)
        text = await self._ask(
            "You plan answers to shopper questions about grocery recall notices. "
            'Reply with JSON only: {"steps": ["...", "...", "..."]} - three short steps.', question, True)
        steps = _json(text).get("steps")
        if not isinstance(steps, list) or not steps or not all(isinstance(s, str) and s.strip() for s in steps):
            raise ValueError("planner model did not return a list of steps")
        return [s.strip() for s in steps[:5]]

    async def write(self, question: str, steps: List[str]) -> str:
        if self.mode == "fast":
            return DRAFT_FAST
        plan = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        text = await self._ask(
            "You write short, safe answers for shoppers about grocery recalls. Use ONLY the question and the plan. "
            "Never invent lot codes, dates, phone numbers or web addresses. At most 80 words, plain text.",
            f"Question: {question}\nPlan:\n{plan}", False)
        if not text:
            raise ValueError("writer model returned no text")
        return text

    async def review(self, question: str, draft: str) -> Tuple[bool, str]:
        if self.mode == "fast":
            return True, "fast mode: deterministic checks only"
        text = await self._ask(
            "You review a draft answer about a grocery recall. Approve only if it answers the question, tells the "
            "shopper not to eat or use the recalled product and to follow the official notice, and invents no lot "
            'codes, dates, phone numbers or web addresses. Reply with JSON only: {"approved": true, "notes": "one sentence"}.',
            f"Question: {question}\nDraft: {draft}", True)
        data = _json(text)
        return bool(data.get("approved")), str(data.get("notes", "")).strip()[:300]


def draft_checks(draft: str) -> dict:
    """Deterministic review rules that apply in every mode."""
    return {"not_empty": bool(draft.strip()),
            "length_20_to_900": 20 <= len(draft.strip()) <= 900,
            "no_url_or_phone_number": URL_OR_PHONE.search(draft) is None}
