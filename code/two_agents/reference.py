"""HW9 Part 4: the reference dataset (ground truth), the notice board the Answering Agent reads, and question analysis.

reference_dataset.json  structured, current facts per recall notice: this is what the Evaluator checks against
notice_board.json       the published notice text (original announcement + dated updates): what the Answering Agent reads
The two are generated together by scripts/build_hw9_part4_data.py from the same seeded records."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

CHANGING = ("units", "lots", "deadline", "states", "status")

INTENT_RULES = [  # (intent, regex over the lower-cased question); a question can ask for several things
    ("units", r"how many|number of units|\bunits\b"),
    ("lots", r"lot code|lot number|\blots?\b|batch"),
    ("deadline", r"deadline|by what date|until what date|last day|by when|refund window"),
    ("states", r"which states|what states|in which states|\bstates\b"),
    ("status", r"still active|\bstatus\b|expanded or closed|\bexpanded\b|\bclosed\b"),
    ("action", r"what should i do|what do i do|should i (?:eat|keep|throw|return)"),
    ("hazard", r"\bwhy\b|what hazard|what is the reason|what was wrong"),
]
UNSUPPORTED_RE = re.compile(r"\bfined\b|\bfines?\b|lawsuit|\bsued?\b|\bceo\b|\bprice\b|\bcost\b|how much does|profit|"
                            r"calories|who owns|founded", re.IGNORECASE)


def load_json(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def detect_intents(question: str) -> list:
    q = question.lower()
    return [name for name, rx in INTENT_RULES if re.search(rx, q)]


def unsupported_topic(question: str) -> bool:
    return bool(UNSUPPORTED_RE.search(question))


def find_notice(question: str, notices: list) -> Optional[dict]:
    """The notice whose product name appears in the question (longest product name wins); None if no notice matches."""
    q = question.lower()
    hits = [n for n in notices if n["product"].lower() in q]
    return max(hits, key=lambda n: len(n["product"])) if hits else None
