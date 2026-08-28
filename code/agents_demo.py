"""Planner -> Reviewer -> deterministic Finalizer pipeline for Homework 1."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.model_client import ModelClientError, ModelResponse, OllamaModelClient


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "had", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or",
    "our", "that", "the", "their", "this", "to", "was", "were", "will", "with",
}

TAG_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "summary": {"type": "string"},
    },
    "required": ["tags", "summary"],
    "additionalProperties": False,
}

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "summary": {"type": "string"},
        "changed": {"type": "boolean"},
        "explanation": {"type": "string"},
    },
    "required": ["tags", "summary", "changed", "explanation"],
    "additionalProperties": False,
}


def words(text: str) -> list[str]:
    """Return lowercase word tokens while preserving internal hyphens."""

    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())


def ngrams(items: list[str], size: int) -> Iterable[tuple[str, ...]]:
    for index in range(len(items) - size + 1):
        yield tuple(items[index:index + size])


def phrase_candidates(title: str, content: str, limit: int = 12) -> list[str]:
    """Derive generic tag candidates only from the supplied title and content."""

    source_words = words(f"{title} {title} {content}")
    content_words = [word for word in source_words if word not in STOP_WORDS and len(word) > 2]
    scored: Counter[str] = Counter()
    for size, weight in ((3, 4), (2, 3)):
        for gram in ngrams(content_words, size):
            scored[" ".join(gram)] += weight
    for word in content_words:
        scored[word] += 1

    ordered = sorted(scored, key=lambda item: (-scored[item], -len(item.split()), item))
    return ordered[:limit]


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse an object, tolerating an accidental Markdown fence or surrounding text."""

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            value = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def normalize_tag(value: Any) -> str:
    tag = " ".join(words(str(value)))
    return " ".join(tag.split()[:5]).strip()


def normalize_summary(value: Any, content: str) -> str:
    summary_words = str(value).replace("…", "").replace("...", "").split()
    if not summary_words:
        summary_words = content.split()
    summary = " ".join(summary_words[:25]).strip().rstrip(".!?")
    return f"{summary}." if summary else "Summary unavailable."


def finalize_payload(payload: Mapping[str, Any], title: str, content: str) -> dict[str, Any]:
    """Deterministically enforce exactly three unique tags and a <=25-word summary."""

    final_tags: list[str] = []
    raw_tags = payload.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []

    for item in [*raw_tags, *phrase_candidates(title, content)]:
        tag = normalize_tag(item)
        if tag and tag not in final_tags:
            final_tags.append(tag)
        if len(final_tags) == 3:
            break

    while len(final_tags) < 3:
        final_tags.append(f"topic {len(final_tags) + 1}")

    return {
        "tags": final_tags,
        "summary": normalize_summary(payload.get("summary", ""), content),
    }


def usage_dict(response: ModelResponse) -> dict[str, int]:
    return {
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "total_tokens": response.total_tokens,
    }


def run_pipeline(
    client: OllamaModelClient,
    title: str,
    content: str,
    temperature: float,
) -> dict[str, Any]:
    """Run two LLM agents followed by deterministic schema enforcement."""

    planner_messages = [
        {
            "role": "system",
            "content": (
                "You are Planner. Derive exactly three specific topical tags and one concise "
                "summary from only the user's title and content. Never use fixed domain keywords. "
                "The summary must be one sentence with at most 25 words. Return only JSON matching "
                f"this schema: {json.dumps(TAG_SUMMARY_SCHEMA, separators=(',', ':'))}"
            ),
        },
        {
            "role": "user",
            "content": f"Title: {title}\nContent: {content}",
        },
    ]

    pipeline_start = time.perf_counter()
    planner_start = time.perf_counter()
    planner_response = client.complete(
        planner_messages,
        temperature=temperature,
        response_format=TAG_SUMMARY_SCHEMA,
    )
    planner_latency_ms = round((time.perf_counter() - planner_start) * 1000, 3)
    planner = finalize_payload(parse_json_object(planner_response.content), title, content)

    reviewer_messages = [
        {
            "role": "system",
            "content": (
                "You are Reviewer. Check that all three tags are distinct, specific, and supported "
                "by the supplied title/content. Check that the summary is one sentence of no more "
                "than 25 words. Correct problems when needed. Set changed to true only when your "
                "tags or summary differ from Planner. Return only JSON matching this schema: "
                f"{json.dumps(REVIEW_SCHEMA, separators=(',', ':'))}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Title: {title}\nContent: {content}\n"
                f"Planner proposal: {json.dumps(planner, ensure_ascii=False)}"
            ),
        },
    ]

    reviewer_start = time.perf_counter()
    reviewer_response = client.complete(
        reviewer_messages,
        temperature=temperature,
        response_format=REVIEW_SCHEMA,
    )
    reviewer_latency_ms = round((time.perf_counter() - reviewer_start) * 1000, 3)
    raw_review = parse_json_object(reviewer_response.content)
    reviewed = finalize_payload(raw_review, title, content)
    changed = reviewed != planner
    explanation = str(raw_review.get("explanation", "")).strip()
    if not explanation:
        explanation = "Reviewer changed the proposal." if changed else "Planner output already met the requirements."

    final = finalize_payload(reviewed, title, content)
    total_latency_ms = round((time.perf_counter() - pipeline_start) * 1000, 3)

    return {
        "input": {"title": title, "content": content},
        "temperature": temperature,
        "model": client.model,
        "transcript": {
            "planner": {
                **planner,
                "latency_ms": planner_latency_ms,
                "usage": usage_dict(planner_response),
            },
            "reviewer": {
                **reviewed,
                "changed": changed,
                "explanation": explanation,
                "latency_ms": reviewer_latency_ms,
                "usage": usage_dict(reviewer_response),
            },
        },
        "final": final,
        "latency_ms": total_latency_ms,
    }


def load_input(path: Path) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    title = str(data.get("title", "")).strip()
    content = str(data.get("content", "")).strip()
    if not title or not content:
        raise ValueError("Input file must contain non-empty title and content strings")
    return title, content


def print_transcript(result: Mapping[str, Any]) -> None:
    transcript = result["transcript"]
    print("\n=== Planner Output ===")
    print(json.dumps(transcript["planner"], indent=2, ensure_ascii=False))
    print("\n=== Reviewer Output ===")
    print(json.dumps(transcript["reviewer"], indent=2, ensure_ascii=False))
    print("\n=== Finalized Output ===")
    print(json.dumps(result["final"], indent=2, ensure_ascii=False))
    print("\n=== Publish Output (valid JSON) ===")
    print(json.dumps({"publish": result["final"]}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--content")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--output-json",
        type=Path,
        help="write the complete machine-readable pipeline result to this path",
    )
    args = parser.parse_args()

    if args.input_file:
        title, content = load_input(args.input_file)
    elif args.title and args.content:
        title, content = args.title.strip(), args.content.strip()
    else:
        parser.error("provide --input-file or both --title and --content")

    client = OllamaModelClient(model=args.model, base_url=args.base_url)
    try:
        result = run_pipeline(client, title, content, args.temperature)
    except ModelClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_transcript(result)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nSaved machine-readable result: {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
