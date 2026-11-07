"""HW9 Part 4: the Answering Agent. Looks up the notice text on the notice board, builds a prompt (plus the lessons, plus the
Evaluator's feedback on a retry) and asks the model."""
from __future__ import annotations

from .lessons import LessonStore
from .llm import LLM
from .reference import find_notice

BASE_SYSTEM = ("You answer questions from shoppers about grocery recall notices. Use the notice text you are given. "
               "Reply in one to three short sentences.")


class AnsweringAgent:
    def __init__(self, llm: LLM, board: list, lessons: LessonStore | None = None) -> None:
        self.llm = llm
        self.board = board
        self.lessons = lessons

    def lookup(self, question: str) -> str:
        """The notice board entry whose product name appears in the question (the agent's only tool)."""
        notice = find_notice(question, self.board)
        return notice["text"] if notice else "No matching recall notice was found."

    def build_prompt(self, question: str, feedback: str | None = None, previous: str | None = None,
                     use_lessons: bool = True) -> tuple:
        system = BASE_SYSTEM
        if use_lessons and self.lessons is not None:
            block = self.lessons.prompt_block()
            if block:
                system = f"{system}\n\n{block}"
        user = f"Recall notice:\n{self.lookup(question)}\n\nQuestion: {question}"
        if feedback:
            user += (f"\n\nYour previous answer was:\n{previous}\n\nA reviewer found a problem: {feedback}\n"
                     "Write a corrected answer.")
        return system, user

    def answer(self, question: str, feedback: str | None = None, previous: str | None = None, use_lessons: bool = True) -> str:
        system, user = self.build_prompt(question, feedback, previous, use_lessons)
        return self.llm(system, user).strip()
