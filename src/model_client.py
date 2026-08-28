"""Stable Ollama model adapter used by every Homework 1 model call."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


Message = Mapping[str, Any]


class ModelClientError(RuntimeError):
    """Raised when Ollama cannot return a usable response."""


@dataclass(frozen=True)
class ModelResponse:
    """Normalized response returned by the stable adapter interface."""

    content: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str
    total_duration_ns: int
    raw: Mapping[str, Any]


@dataclass
class UsageTotals:
    """Cumulative usage for one client instance."""

    turn_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, int]:
        data = asdict(self)
        data["total_tokens"] = self.total_tokens
        return data


class OllamaModelClient:
    """Small dependency-free adapter around Ollama's `/api/chat` endpoint.

    The public `complete(messages, tools=None)` interface is intentionally stable.
    Optional keyword arguments expose the controls needed by the experiments.
    """

    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 300.0,
        num_ctx: int = 8192,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.usage = UsageTotals()

    def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]] | None = None,
        *,
        temperature: float = 0.0,
        response_format: str | Mapping[str, Any] | None = None,
    ) -> ModelResponse:
        """Return one non-streaming completion and update cumulative token totals."""

        normalized_messages = self._validate_messages(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": normalized_messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
            },
        }
        if tools is not None:
            payload["tools"] = list(tools)
        if response_format is not None:
            payload["format"] = response_format

        data = self._post_json("/api/chat", payload)
        message = data.get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
            raise ModelClientError("Ollama response did not include message.content")

        input_tokens = self._nonnegative_int(data.get("prompt_eval_count"))
        output_tokens = self._nonnegative_int(data.get("eval_count"))
        self.usage.turn_count += 1
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens

        return ModelResponse(
            content=message["content"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=str(data.get("model", self.model)),
            total_duration_ns=self._nonnegative_int(data.get("total_duration")),
            raw=data,
        )

    def stats(self) -> dict[str, int]:
        """Return a copy of cumulative counters."""

        return self.usage.to_dict()

    def check_connection(self) -> dict[str, Any]:
        """Check that Ollama is reachable and return `/api/tags` data."""

        request = Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urlopen(request, timeout=min(self.timeout_seconds, 15.0)) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelClientError(
                f"Cannot reach Ollama at {self.base_url}. Start Ollama and pull {self.model}."
            ) from exc

    def _post_json(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ModelClientError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise ModelClientError(
                f"Cannot reach Ollama at {self.base_url}. Start Ollama and pull {self.model}."
            ) from exc
        except json.JSONDecodeError as exc:
            raise ModelClientError("Ollama returned invalid JSON") from exc

        if not isinstance(decoded, dict):
            raise ModelClientError("Ollama returned a non-object response")
        if decoded.get("error"):
            raise ModelClientError(f"Ollama error: {decoded['error']}")
        return decoded

    @staticmethod
    def _validate_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
        if not messages:
            raise ValueError("messages must contain at least one message")

        normalized: list[dict[str, Any]] = []
        valid_roles = {"system", "user", "assistant", "tool"}
        for index, message in enumerate(messages):
            role = message.get("role")
            content = message.get("content")
            if role not in valid_roles:
                raise ValueError(f"message {index} has invalid role: {role!r}")
            if not isinstance(content, str):
                raise ValueError(f"message {index} content must be a string")
            normalized.append(dict(message))
        return normalized

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
