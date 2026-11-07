"""HW9 Part 3: objective check of an answer against the database fact it should contain (no model involved)."""
from __future__ import annotations

import re
from typing import Optional


def answer_has_fact(answer: Optional[str], fact: Optional[dict]) -> Optional[bool]:
    """True/False whether the answer states the fact; None when the case has no fact (unrelated questions).

    units: the number, written 31863 or 31,863, not as part of a longer number.
    agency: the reporting agency's name, ignoring case."""
    if not fact:
        return None
    if not answer:
        return False
    if fact["aspect"] == "units":
        v = int(fact["value"])
        for form in (str(v), f"{v:,}"):
            if re.search(rf"(?<![\d,.]){re.escape(form)}(?![\d]|,\d)", answer):
                return True
        return False
    return str(fact["value"]).lower() in answer.lower()
