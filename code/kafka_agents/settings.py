"""HW8 Part 2/3 - topics, consumer groups and the switches the Part 3 failure tests flip.

Pipeline (no agent calls another agent; Kafka is the only link):
    send_question -> s9619_inbox -> Planner -> s9619_tasks (2 partitions) -> Writer -> s9619_drafts
                  -> Reviewer -> s9619_final
    messages that cannot be processed after the retry limit go to s9619_dead_letter
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from kafka_api.config import PREFIX

INBOX_TOPIC = f"{PREFIX}_inbox"
TASKS_TOPIC = f"{PREFIX}_tasks"
DRAFTS_TOPIC = f"{PREFIX}_drafts"
FINAL_TOPIC = f"{PREFIX}_final"
DEAD_LETTER_TOPIC = f"{PREFIX}_dead_letter"

TASKS_PARTITIONS = 2
PLANNER_GROUP = f"{PREFIX}-planner"
WRITER_GROUP = f"{PREFIX}-writer"      # every Writer instance joins this one group and shares the partitions
REVIEWER_GROUP = f"{PREFIX}-reviewer"

BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW8 Part 2/3 (three Kafka agents)"


@dataclass(frozen=True)
class Flags:
    """Behaviour switches (environment variables). Defaults are the safe, final behaviour; the Part 3
    'before' runs set one switch to its naive value to show what goes wrong without the protection."""

    mode: str = "llm"             # HW8_AGENT_MODE: llm = qwen3:8b via Ollama, fast = deterministic text (tests)
    idempotent: bool = True       # HW8_IDEMPOTENT=0: a replayed correlation_id is processed again
    commit_mode: str = "after"    # HW8_COMMIT_MODE=before: offset committed on receipt, before the work is done
    max_attempts: int = 3         # HW8_MAX_ATTEMPTS: tries per message; 0 = retry forever (no dead-letter)
    task_key: str = "entity"      # HW8_TASK_KEY=none: tasks are spread over partitions without a key
    write_delay_s: float = 0.0    # HW8_WRITE_DELAY_S: fast-mode pause per draft (room to kill the Writer)
    jitter_s: float = 0.0         # HW8_JITTER_S: extra seeded pause per message (makes the ordering test visible)
    retry_backoff_s: float = 0.5  # HW8_RETRY_BACKOFF_S: pause between attempts
    state_dir: Optional[str] = None  # HW8_STATE_DIR: keep the processed-id list on disk so it survives a restart


def _bool(value: str) -> bool:
    return value.strip().lower() not in ("0", "false", "no", "off", "")


def load_flags(env: Optional[Mapping[str, str]] = None) -> Flags:
    e = os.environ if env is None else env
    d = Flags()
    return Flags(
        mode=e.get("HW8_AGENT_MODE", d.mode).strip().lower(),
        idempotent=_bool(e.get("HW8_IDEMPOTENT", "1")),
        commit_mode=e.get("HW8_COMMIT_MODE", d.commit_mode).strip().lower(),
        max_attempts=int(e.get("HW8_MAX_ATTEMPTS", d.max_attempts)),
        task_key=e.get("HW8_TASK_KEY", d.task_key).strip().lower(),
        write_delay_s=float(e.get("HW8_WRITE_DELAY_S", d.write_delay_s)),
        jitter_s=float(e.get("HW8_JITTER_S", d.jitter_s)),
        retry_backoff_s=float(e.get("HW8_RETRY_BACKOFF_S", d.retry_backoff_s)),
        state_dir=e.get("HW8_STATE_DIR") or None,
    )
