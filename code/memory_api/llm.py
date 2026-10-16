"""HW6 Part 2 - model access. Chat goes through the HW1 adapter (src/model_client.py,
OllamaModelClient); embeddings use Ollama's /api/embed on the same local server.

The services are tiny classes so tests can swap in fakes (see scripts/test_memory_api_hw06.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import config

# The HW1 adapter lives in <repo>/src (copied to /app/src in the Docker image).
_ROOTS = [Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[1]]
for _root in _ROOTS:
    if (_root / "src" / "model_client.py").exists() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from src.model_client import ModelClientError, ModelResponse, OllamaModelClient  # noqa: E402


class ChatModel:
    """Wraps the HW1 adapter so every call returns the same small result."""

    def __init__(self) -> None:
        self.client = OllamaModelClient(
            model=config.CHAT_MODEL,
            base_url=config.OLLAMA_BASE_URL,
            timeout_seconds=config.OLLAMA_TIMEOUT_SECONDS,
            num_ctx=config.NUM_CTX,
        )

    def complete(self, messages: Sequence[Mapping[str, Any]], *, json_schema: Mapping[str, Any] | None = None) -> ModelResponse:
        return self.client.complete(
            messages, temperature=config.CHAT_TEMPERATURE, response_format=json_schema
        )


class Embedder:
    """nomic-embed-text through Ollama /api/embed (one text in, one float list out)."""

    def embed(self, text: str) -> list[float]:
        body = json.dumps({"model": config.EMBED_MODEL, "input": text}).encode("utf-8")
        request = Request(
            f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=config.OLLAMA_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ModelClientError(f"Ollama embed HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc
        except (URLError, TimeoutError) as exc:
            raise ModelClientError(f"Cannot reach Ollama at {config.OLLAMA_BASE_URL} for embeddings") from exc
        embeddings = data.get("embeddings")
        if not embeddings or not isinstance(embeddings[0], list):
            raise ModelClientError(f"Ollama embed returned no vector (is {config.EMBED_MODEL} pulled?)")
        return [float(x) for x in embeddings[0]]


_chat_singleton: ChatModel | None = None
_embed_singleton: Embedder | None = None


def get_chat_model() -> ChatModel:
    global _chat_singleton
    if _chat_singleton is None:
        _chat_singleton = ChatModel()
    return _chat_singleton


def get_embedder() -> Embedder:
    global _embed_singleton
    if _embed_singleton is None:
        _embed_singleton = Embedder()
    return _embed_singleton
