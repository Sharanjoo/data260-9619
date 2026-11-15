"""HW10 Part 2: the judge. A DeepEval custom model that talks to a LOCAL Ollama model (default qwen3:8b), so no data
leaves the laptop and no API key is needed.

Bounded on purpose: every call has a timeout, at most ``retries`` extra attempts, and any failure is raised as
JudgeError. The evaluator catches JudgeError per metric and records score=null + the error, so a malformed message or
an unavailable Ollama can never hang the run. Temperature is 0 and thinking is off (the HW1 adapter sets think=false).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))  # appended, not inserted: the repo's own `code/` package must not shadow the stdlib

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # no usage data sent anywhere

from deepeval.models import DeepEvalBaseLLM  # noqa: E402

from src.model_client import OllamaModelClient  # noqa: E402  (the HW1 adapter)

JUDGE_MODEL = os.environ.get("HW10_JUDGE_MODEL", "qwen3:8b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
JUDGE_TIMEOUT_S = float(os.environ.get("HW10_JUDGE_TIMEOUT", "240"))
JUDGE_RETRIES = int(os.environ.get("HW10_JUDGE_RETRIES", "1"))
JUDGE_SYSTEM = ("You are a strict, consistent grader. Follow the evaluation steps exactly. "
                "Reply with a single JSON object and nothing else.")


class JudgeError(RuntimeError):
    """The judge could not produce a usable answer within its time and retry budget."""


def parse_json_object(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("judge reply is not JSON") from None
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("judge reply is not a JSON object")
    return data


class OllamaJudge(DeepEvalBaseLLM):
    def __init__(self, model: str = JUDGE_MODEL, base_url: str = OLLAMA_URL, timeout_s: float = JUDGE_TIMEOUT_S,
                 retries: int = JUDGE_RETRIES, client: Optional[Any] = None) -> None:
        self.model_id, self.base_url, self.timeout_s, self.retries = model, base_url, timeout_s, retries
        self._client = client
        self.calls = 0
        self.failures = 0
        super().__init__(model=model)

    def load_model(self) -> Any:
        if self._client is None:
            self._client = OllamaModelClient(model=self.model_id, base_url=self.base_url,
                                             timeout_seconds=self.timeout_s)
        return self._client

    def get_model_name(self, *args: Any, **kwargs: Any) -> str:
        return f"ollama/{self.model_id}"

    def generate(self, prompt: str, schema: Optional[Any] = None, **kwargs: Any) -> Any:
        fmt: Any = schema.model_json_schema() if schema is not None else "json"
        messages = [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}]
        last = "no attempt made"
        for _ in range(self.retries + 1):
            self.calls += 1
            try:
                reply = self.model.complete(messages, temperature=0.0, response_format=fmt)
                data = parse_json_object(reply.content)
                return schema.model_validate(data) if schema is not None else json.dumps(data)
            except Exception as exc:  # noqa: BLE001 - timeouts, HTTP errors, bad JSON, wrong fields
                last = f"{type(exc).__name__}: {exc}"
        self.failures += 1
        raise JudgeError(last)

    async def a_generate(self, prompt: str, schema: Optional[Any] = None, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self.generate, prompt, schema)
