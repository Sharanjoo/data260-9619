"""HW9 Part 4: the language-model call. qwen3:8b through the Ollama HTTP API (standard library only, no extra package).

An LLM here is any callable (system_prompt, user_prompt) -> text, so the tests can pass a fake model."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable

LLM = Callable[[str, str], str]
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaLLM:
    def __init__(self, model: str | None = None, base_url: str | None = None, seed: int = 9619, timeout_s: int = 300) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        self.base_url = (base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.seed = seed
        self.timeout_s = timeout_s
        self.calls = 0

    def __call__(self, system: str, user: str) -> str:
        body = {"model": self.model, "stream": False, "think": False,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "options": {"temperature": 0, "seed": self.seed, "num_predict": 400}}
        try:
            data = self._post(body)
        except urllib.error.HTTPError as err:
            if err.code != 400:
                raise
            body.pop("think")  # a model without a thinking mode rejects the field
            data = self._post(body)
        self.calls += 1
        return THINK_RE.sub("", data["message"]["content"]).strip()

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(f"{self.base_url}/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
