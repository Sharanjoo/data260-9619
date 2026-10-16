"""HW6 Part 2/3 - prompt assembly and the per-component token accounting.

Prompt order (as the assignment asks): system primer + long-term summaries +
short-term window + current message + episodic facts.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import config


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 characters per token). Only used to split the model's REAL
    prompt token count between components; see split_prompt_tokens()."""
    return math.ceil(len(text) / 4) if text else 0


def _first_sentence(text: str, limit: int = 120) -> str:
    match = re.match(r"(.+?[.!?])(\s|$)", text.strip(), flags=re.S)
    sentence = (match.group(1) if match else text.strip())
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def apply_window_policy(history: List[Dict[str, Any]], policy: str) -> List[Dict[str, Any]]:
    """Part 3 compression policy. 'none' keeps the plain sliding window.
    'compress_old_assistant' keeps the 2 most recent history messages verbatim and shrinks
    every older assistant reply to its first sentence (user messages stay intact because
    they carry the facts)."""
    if policy != "compress_old_assistant":
        return history
    keep_from = max(0, len(history) - 2)
    out = []
    for index, message in enumerate(history):
        if index < keep_from and message["role"] == "assistant":
            out.append({"role": "assistant", "content": _first_sentence(message["content"])})
        else:
            out.append(message)
    return out


def long_term_text(lifetime: Optional[str], session: Optional[str]) -> str:
    parts = []
    if lifetime:
        parts.append(f"Lifetime summary of this user:\n{lifetime}")
    if session:
        parts.append(f"Summary of this conversation so far:\n{session}")
    return "\n\n".join(parts)


def episodic_text(episodes: Sequence[Dict[str, Any]]) -> str:
    if not episodes:
        return ""
    ordered = sorted(episodes, key=lambda e: e.get("created_at", ""))
    return (
        "Remembered facts about this user (oldest first; a newer fact replaces an older one):\n"
        + "\n".join(f"- {e['fact']}" for e in ordered)
    )


def build_messages(
    window: List[Dict[str, Any]],
    current_message: str,
    lifetime: Optional[str],
    session_summary: Optional[str],
    episodes: Sequence[Dict[str, Any]],
    policy: str = "none",
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """`window` is the short-term window, oldest first, whose LAST item is the current user message."""
    history = [{"role": m["role"], "content": m["content"]} for m in window[:-1]]
    history = apply_window_policy(history, policy)
    lt = long_term_text(lifetime, session_summary)
    ep = episodic_text(episodes)

    system = config.SYSTEM_PRIMER + (f"\n\n{lt}" if lt else "")
    final_user = current_message + (f"\n\n{ep}" if ep else "")
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": final_user}]
    texts = {
        "system_primer": config.SYSTEM_PRIMER,
        "long_term_summary": lt,
        "short_term_window": "\n".join(m["content"] for m in history),
        "episodic_facts": ep,
        "current_message": current_message,
    }
    return messages, texts


def split_prompt_tokens(texts: Dict[str, str], actual_prompt_tokens: int) -> Dict[str, int]:
    """Ollama reports ONE prompt_eval_count for the whole prompt. To get a per-component split we
    estimate each component (chars/4) and scale the estimates so they add up to the real total."""
    estimates = {name: estimate_tokens(text) for name, text in texts.items()}
    total = sum(estimates.values())
    if total == 0 or actual_prompt_tokens <= 0:
        return {name: 0 for name in estimates}
    scaled = {name: int(value * actual_prompt_tokens / total) for name, value in estimates.items()}
    remainder = actual_prompt_tokens - sum(scaled.values())
    if remainder:
        biggest = max(scaled, key=lambda name: estimates[name])
        scaled[biggest] += remainder
    return scaled
