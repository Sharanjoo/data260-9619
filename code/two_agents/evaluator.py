"""HW9 Part 4: the Evaluator Agent.

A rule-based judge (no model): it compares an answer with the reference dataset, which holds the CURRENT facts of every
recall notice. It returns pass / fail, the failure pattern, and feedback for the retry that says what is wrong without
giving the correct value away.

Failure patterns (the keys the lessons are created from):
  stale_value        the answer states the original value of something the notice has since updated (units, lot codes,
                     states, refund deadline, status) and not the current one
  incomplete_multi   the question asks for several things and the answer covers only some of them
  missing_value      the requested fact is not in the answer (or the answer refuses although the notice has it)
  fabricated_answer  the question cannot be answered from the notices (unknown product, or fines/CEO/price questions) and
                     the answer does not say so, or it invents numbers, lot codes, dates or links"""
from __future__ import annotations

from . import textmatch as tm
from .reference import detect_intents, find_notice, unsupported_topic

PATTERNS = ("stale_value", "incomplete_multi", "missing_value", "fabricated_answer")
LABEL = {"units": "number of affected units", "lots": "lot codes", "deadline": "refund deadline",
         "states": "states where it was sold", "status": "recall status", "action": "what the customer should do",
         "hazard": "reason for the recall"}


def _check(intent: str, notice: dict, answer: str) -> tuple:
    """(ok, stale) for one requested fact. stale = the answer shows the original value instead of the current one."""
    if intent == "units":
        cur, old = notice["units_affected"]["current"], notice["units_affected"]["initial"]
        ok = tm.has_number(answer, cur)
        return ok, (not ok and cur != old and tm.has_number(answer, old))
    if intent == "lots":
        cur, old = notice["lot_codes"]["current"], notice["lot_codes"]["initial"]
        ok = all(tm.has_lot(answer, c) for c in cur)
        return ok, (not ok and cur != old and any(tm.has_lot(answer, c) for c in old))
    if intent == "deadline":
        cur, old = notice["refund_deadline"]["current"], notice["refund_deadline"]["initial"]
        ok = tm.has_date(answer, cur)
        return ok, (not ok and cur != old and tm.has_date(answer, old))
    if intent == "states":
        cur, old = notice["states"]["current"], notice["states"]["initial"]
        ok = all(tm.has_state(answer, s) for s in cur)
        return ok, (not ok and cur != old and any(tm.has_state(answer, s) for s in old))
    if intent == "status":
        cur = notice["status"]["current"]
        if cur == "expanded":
            ok = tm.has_any(answer, ["expanded", "expansion"])
            return ok, (not ok and tm.has_any(answer, ["active", "ongoing"]))
        return tm.has_any(answer, ["active", "ongoing", "open"]), False
    if intent == "hazard":
        return tm.has_any(answer, notice["hazard_keywords"]), False
    if intent == "action":
        return all(tm.has_any(answer, group) for group in notice["action_check"]), False
    raise ValueError(intent)


class Evaluator:
    def __init__(self, notices: list) -> None:
        self.notices = notices

    def expected_scope(self, question: str) -> str:
        """'answerable' when the notices hold the answer, else 'refuse'."""
        return "refuse" if (find_notice(question, self.notices) is None or unsupported_topic(question)) else "answerable"

    def evaluate(self, question: str, answer: str) -> dict:
        notice = find_notice(question, self.notices)
        if self.expected_scope(question) == "refuse":
            invented = bool(tm.BIG_NUMBER.search(answer) or tm.LOT_LIKE.search(answer) or tm.ISO_DATE.search(answer)
                            or tm.URL_OR_PHONE.search(answer))
            ok = tm.is_refusal(answer) and not invented
            return {"passed": ok, "pattern": None if ok else "fabricated_answer", "scope": "refuse",
                    "failed_intents": [] if ok else ["out_of_scope"],
                    "detail": "" if ok else ("invented details" if invented else "did not say the information is unavailable"),
                    "feedback": "" if ok else ("The recall notices do not contain this information. Say so plainly and do not "
                                               "give numbers, lot codes, dates, links or names that are not in a notice.")}
        intents = detect_intents(question) or ["units"]
        results = {i: _check(i, notice, answer) for i in intents}
        failed = [i for i, (ok, _) in results.items() if not ok]
        if not failed:
            return {"passed": True, "pattern": None, "scope": "answerable", "failed_intents": [], "detail": "", "feedback": ""}
        stale = [i for i in failed if results[i][1]]
        if stale:
            pattern = "stale_value"
        elif len(intents) > 1 and len(failed) < len(intents):
            pattern = "incomplete_multi"
        else:
            pattern = "missing_value"
        names = ", ".join(LABEL[i] for i in failed)
        if pattern == "stale_value":
            feedback = (f"Your answer gives an outdated value for: {', '.join(LABEL[i] for i in stale)}. The notice was updated "
                        "after it was first published. Use the values from the most recent UPDATE in the notice.")
        elif pattern == "incomplete_multi":
            feedback = (f"Your answer leaves out part of the question: {names}. The question asks for more than one thing; "
                        "answer every part, using the notice.")
        elif "action" in failed:
            feedback = ("Your answer does not give the full advice for customers. State clearly whether the product may be "
                        "eaten or used and what to do with it, as the notice says in its 'What to do' sentence.")
        else:
            feedback = (f"Your answer does not state the {names} that the notice contains. Re-read the notice and give it, "
                        "exactly as written there.")
        return {"passed": False, "pattern": pattern, "scope": "answerable", "failed_intents": failed,
                "detail": f"{pattern}: {names}", "feedback": feedback}
