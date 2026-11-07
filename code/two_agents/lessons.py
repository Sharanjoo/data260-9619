"""HW9 Part 4: the lessons file. Each lesson records a failure pattern the Evaluator found and the correction that is
added to the Answering Agent's prompt from then on.

lessons.json = {"lessons": [ {lesson_id, failure_pattern, correction, created_at, use_count} ], "occurrences": {pattern: n}}
A lesson is created when the same failure pattern has been seen LESSON_MIN_OCCURRENCES times (2) on training questions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LESSON_MIN_OCCURRENCES = 2
CORRECTIONS = {
    "stale_value": ("A notice can contain an original announcement followed by one or more UPDATE lines. The UPDATE replaces the "
                    "original figures. Always report units, lot codes, states, refund deadline and status from the most recent "
                    "UPDATE, and never from the original announcement. Say that the figure comes from the update."),
    "incomplete_multi": ("When a question asks for two things (for example units and a refund date, or lot codes and states), "
                         "answer both parts in the same reply. Check each part of the question against your answer before "
                         "you finish."),
    "missing_value": ("Look for the exact fact the question asks about in the notice text and state it in the answer, written "
                      "as in the notice. Do not reply that the information is missing when the notice contains it."),
    "fabricated_answer": ("Answer only from the notice text. If no notice is provided, or the question is about something a recall "
                          "notice never contains (fines, lawsuits, prices, company executives), say that you do not have that "
                          "information. Never invent numbers, lot codes, dates or links."),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LessonStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.lessons: list = []
        self.occurrences: dict = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.lessons = data.get("lessons", [])
            self.occurrences = data.get("occurrences", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"lessons": self.lessons, "occurrences": self.occurrences}, indent=2, ensure_ascii=False),
                             encoding="utf-8")

    def has(self, pattern: str) -> bool:
        return any(x["failure_pattern"] == pattern for x in self.lessons)

    def record_failure(self, pattern: str) -> dict | None:
        """Count one occurrence; create the lesson when the pattern has been seen LESSON_MIN_OCCURRENCES times."""
        self.occurrences[pattern] = self.occurrences.get(pattern, 0) + 1
        if self.occurrences[pattern] >= LESSON_MIN_OCCURRENCES and not self.has(pattern):
            lesson = {"lesson_id": f"L{len(self.lessons) + 1:03d}", "failure_pattern": pattern,
                      "correction": CORRECTIONS[pattern], "created_at": now_iso(), "use_count": 0}
            self.lessons.append(lesson)
            return lesson
        return None

    def remove(self, lesson_id: str) -> None:
        self.lessons = [x for x in self.lessons if x["lesson_id"] != lesson_id]

    def only(self, lesson_ids: list) -> "LessonStore":
        """An in-memory copy holding just these lessons (used by the validation gate); does not write to disk."""
        copy = LessonStore(self.path.with_name("_unused_" + self.path.name))
        copy.lessons = [dict(x) for x in self.lessons if x["lesson_id"] in lesson_ids]
        return copy

    def prompt_block(self, mark_used: bool = True) -> str:
        if not self.lessons:
            return ""
        lines = ["Lessons learned from earlier mistakes (follow them):"]
        for x in self.lessons:
            lines.append(f"- {x['correction']}")
            if mark_used:
                x["use_count"] = x.get("use_count", 0) + 1
        return "\n".join(lines)
