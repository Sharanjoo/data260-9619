"""HW9 Part 4: the two-agent loop. The Answering Agent answers, the Evaluator checks the answer against the reference dataset;
on a failure the Answering Agent gets the Evaluator's feedback and tries once more (at most MAX_ATTEMPTS = 2)."""
from __future__ import annotations

import time

from .answerer import AnsweringAgent
from .evaluator import Evaluator

MAX_ATTEMPTS = 2


class TwoAgentSystem:
    def __init__(self, answerer: AnsweringAgent, evaluator: Evaluator) -> None:
        self.answerer = answerer
        self.evaluator = evaluator

    def run(self, qid: str, question: str, retry: bool = True, use_lessons: bool = True,
            first_answer: str | None = None) -> dict:
        """One question through the loop. first_answer forces the first attempt (the controlled bad-answer demo)."""
        attempts = []
        answer, verdict, feedback, previous = "", {}, None, None
        for n in range(1, (MAX_ATTEMPTS if retry else 1) + 1):
            started = time.perf_counter()
            if n == 1 and first_answer is not None:
                answer = first_answer
            else:
                answer = self.answerer.answer(question, feedback, previous, use_lessons)
            elapsed = time.perf_counter() - started
            verdict = self.evaluator.evaluate(question, answer)
            attempts.append({"attempt": n, "answer": answer, "passed": verdict["passed"], "pattern": verdict["pattern"],
                             "detail": verdict["detail"], "feedback": verdict["feedback"], "seconds": round(elapsed, 2),
                             "forced": n == 1 and first_answer is not None})
            if verdict["passed"]:
                break
            feedback, previous = verdict["feedback"], answer
        return {"id": qid, "question": question, "scope": verdict["scope"], "attempts": attempts,
                "passed_first": attempts[0]["passed"], "passed_final": attempts[-1]["passed"],
                "n_attempts": len(attempts), "first_pattern": attempts[0]["pattern"]}
