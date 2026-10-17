"""HW6 Part 4 - file-based memory: AGENT.md (durable instructions) and MEMORY.md (durable facts).

The functions here load both files, put them into the system prompt, read the recorded
"last consolidated" time, decide when MEMORY.md must be consolidated, consolidate it, and
implement the /memory, /compact, /dream and /help commands.

MEMORY.md format
    # MEMORY.md
    <!-- last-consolidated: 2026-10-16T12:00:00Z -->
    ## Facts
    - [2026-10-05] The user lives in Oakland.
    - [2026-09-02] [critical] The user has a severe peanut allergy.
    ## Resolved conflicts
    - KEPT L7 ... | SUPERSEDED L3 ... | reason

A "memory line" is a non-empty line that is not part of an HTML comment (<!-- ... -->).
Headings and bullets both count. Consolidation is due when MEMORY.md has MORE than 40
memory lines or its recorded consolidation time is more than 24 hours old.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

MEMORY_LINE_LIMIT = 40
CONSOLIDATION_MAX_AGE = timedelta(hours=24)
RESULT_LINE_LIMIT = 40  # a consolidated file must have FEWER physical lines than this
TIMESTAMP_PATTERN = re.compile(r"<!--\s*last-consolidated:\s*(\S+?)\s*(?:\||-->)")
FACT_PATTERN = re.compile(r"^-\s+(?:\[(\d{4}-\d{2}-\d{2})\]\s*)?(.*?)\s*$")
INLINE_COMMENT = re.compile(r"\s*<!--.*?-->")
FORMAT_HINT = "<!-- format: one fact per bullet '- [YYYY-MM-DD] text'; tag [critical] for safety facts -->"
FACTS_HEADING = "## Facts"
CONFLICTS_HEADING = "## Resolved conflicts"

AGENT_FILE = "AGENT.md"
MEMORY_FILE = "MEMORY.md"

BASE_SYSTEM_PROMPT = (
    "You are the project assistant for a DATA-260 homework repository. "
    "Follow the instructions in AGENT.md exactly. MEMORY.md lists durable facts from earlier "
    "conversations: use them when relevant, never invent facts that are not there, and treat "
    "facts tagged [critical] (allergies, safety) as must-not-forget."
)

HELP_TEXT = """Available commands:
  /memory   show the current file-based memory (AGENT.md summary, MEMORY.md, consolidation status)
  /compact  consolidate MEMORY.md now (merge duplicates, resolve contradictions) and report line counts before and after
  /dream    pick durable long-term facts out of the recent conversation and add them to MEMORY.md
  /help     show this list
  /quit     leave the chat
Anything else is sent to the model with AGENT.md and MEMORY.md in its system prompt."""

CONSOLIDATION_PROMPT = (
    "You consolidate a Markdown memory file. Each input line is a fact written as "
    "'L<number>: [date] text'. Find the lines that are NOT simply kept and list ONLY those, "
    "using these actions:\n"
    "- merge: the line says the same thing as another line (a duplicate or paraphrase). "
    "target = the line to keep (prefer the most complete or most recent).\n"
    "- supersede: the line contradicts a NEWER line that clearly replaces it (for example a "
    "changed address or setting). target = the newer line.\n"
    "- review: two lines contradict each other and you cannot tell which is right (for example "
    "the newer one is a joke, a guess or unverified). Put the doubtful line here; target = the other line.\n"
    "Rules: a fact with different details (different number, name or place) is NOT a duplicate. "
    "Lines tagged [critical] (allergies, safety) must never be superseded by an unverified "
    "statement. Never drop a fact because it seems unimportant. If unsure, leave the line out of "
    "your answer (it is kept). The line and the target must be two DIFFERENT lines about the same "
    "topic. Copy three to six distinctive words from each of the two lines, exactly as written, into "
    "line_quote and target_quote. Keep each reason under 12 words. "
    "Return JSON: {\"decisions\": [{\"line\": int, \"line_quote\": str, \"action\": \"merge|supersede|review\", "
    "\"target\": int, \"target_quote\": str, \"reason\": str}]}."
)
CONSOLIDATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "line_quote": {"type": "string"},
                    "action": {"type": "string", "enum": ["merge", "supersede", "review"]},
                    "target": {"type": "integer"},
                    "target_quote": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["line", "line_quote", "action", "target", "target_quote", "reason"],
            },
        }
    },
    "required": ["decisions"],
}
DREAM_PROMPT = (
    "You read a recent conversation and the current MEMORY.md. Pick up to 5 durable long-term "
    "facts worth remembering in future conversations (user preferences, decisions, constraints, "
    "project settings, people, allergies). Skip chit-chat, questions, one-off requests and anything "
    "already in MEMORY.md. Write each as one short sentence. Mark critical=true only for safety "
    "facts such as allergies. Return JSON {\"facts\": [{\"fact\": str, \"critical\": bool}]}; "
    "use an empty list when nothing is worth keeping."
)
DREAM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {"fact": {"type": "string"}, "critical": {"type": "boolean"}},
                "required": ["fact", "critical"],
            },
        }
    },
    "required": ["facts"],
}


# --------------------------------------------------------------------------- loading
def load_agent_md(path: Path | str = AGENT_FILE) -> str:
    """Return the text of AGENT.md, or an empty string when the file does not exist."""
    file = Path(path)
    return file.read_text(encoding="utf-8") if file.is_file() else ""


def load_memory_md(path: Path | str = MEMORY_FILE) -> str:
    """Return the text of MEMORY.md, or an empty string when the file does not exist."""
    file = Path(path)
    return file.read_text(encoding="utf-8") if file.is_file() else ""


def load_memory_files(agent_path: Path | str = AGENT_FILE, memory_path: Path | str = MEMORY_FILE) -> Tuple[str, str]:
    """Load AGENT.md and MEMORY.md and return them as (agent_text, memory_text)."""
    return load_agent_md(agent_path), load_memory_md(memory_path)


# --------------------------------------------------------------------------- line counting
def comment_flags(text: str) -> List[bool]:
    """Return one flag per physical line: True when the line belongs to an HTML comment."""
    flags: List[bool] = []
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        starts = stripped.startswith("<!--")
        if inside or starts:
            flags.append(True)
            if "-->" in stripped:
                inside = False
            else:
                inside = True
        else:
            flags.append(False)
    return flags


def memory_lines(text: str) -> List[str]:
    """Return the non-empty, non-comment lines of a memory file."""
    flags = comment_flags(text)
    return [line for line, is_comment in zip(text.splitlines(), flags) if line.strip() and not is_comment]


def count_memory_lines(text: str) -> int:
    """Count the non-empty, non-comment lines of a memory file."""
    return len(memory_lines(text))


def strip_comments(text: str) -> str:
    """Remove comment lines and inline comments so they do not use prompt tokens."""
    flags = comment_flags(text)
    kept = [INLINE_COMMENT.sub("", line).rstrip() for line, c in zip(text.splitlines(), flags) if not c]
    return "\n".join(kept).strip()


# --------------------------------------------------------------------------- timestamp + trigger
def read_last_consolidated(text: str) -> Optional[datetime]:
    """Read the recorded last-consolidated time from MEMORY.md, or None when it is missing or invalid."""
    match = TIMESTAMP_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(1).replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def format_timestamp(moment: datetime) -> str:
    """Format a time as an ISO-8601 UTC string with a trailing Z."""
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp_consolidated(text: str, moment: datetime) -> str:
    """Return the text with its last-consolidated comment set to the given time."""
    stamp = f"<!-- last-consolidated: {format_timestamp(moment)} -->"
    if TIMESTAMP_PATTERN.search(text):
        return re.sub(r"<!--\s*last-consolidated:[^>]*-->", stamp, text, count=1)
    lines = text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    lines.insert(insert_at, stamp)
    return "\n".join(lines) + "\n"


def consolidation_reasons(text: str, now: Optional[datetime] = None) -> List[str]:
    """Return why consolidation is required (an empty list means it is not required)."""
    now = now or datetime.now(timezone.utc)
    reasons: List[str] = []
    lines = count_memory_lines(text)
    if lines > MEMORY_LINE_LIMIT:
        reasons.append(f"{lines} memory lines (limit {MEMORY_LINE_LIMIT})")
    last = read_last_consolidated(text)
    if last is None:
        if lines > 0:
            reasons.append("no consolidation time recorded")
    elif now - last > CONSOLIDATION_MAX_AGE:
        hours = (now - last).total_seconds() / 3600
        reasons.append(f"last consolidated {hours:.1f} hours ago (limit 24)")
    return reasons


def needs_consolidation(text: str, now: Optional[datetime] = None) -> bool:
    """Return True when MEMORY.md has more than 40 memory lines or was consolidated over 24 hours ago."""
    return bool(consolidation_reasons(text, now))


# --------------------------------------------------------------------------- system prompt
def build_system_prompt(agent_text: str, memory_text: str, base: str = BASE_SYSTEM_PROMPT) -> str:
    """Build the system prompt: base instructions, then AGENT.md, then MEMORY.md (comments removed)."""
    parts = [base]
    if agent_text.strip():
        parts.append("## AGENT.md (durable instructions)\n" + strip_comments(agent_text))
    if memory_text.strip():
        parts.append("## MEMORY.md (durable facts)\n" + strip_comments(memory_text))
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- consolidation
@dataclass
class Fact:
    """One fact line parsed from MEMORY.md."""

    line_no: int
    date: str
    text: str
    critical: bool
    audit: str = ""  # inline comment kept from an earlier consolidation pass


@dataclass
class ConsolidationReport:
    """What a consolidation run did, with the numbers /compact prints."""

    before_lines: int
    after_lines: int
    before_physical: int
    after_physical: int
    before_facts: int
    after_facts: int
    merged: int
    superseded: int
    flagged_for_review: int
    passes: int
    guard_notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    under_limit: bool = False
    proposed: List[List[Dict[str, Any]]] = field(default_factory=list)  # the model's raw decisions, one list per pass

    def summary(self) -> str:
        lines = [
            f"Before: {self.before_lines} memory lines ({self.before_facts} facts, {self.before_physical} file lines)",
            f"After:  {self.after_lines} memory lines ({self.after_facts} facts, {self.after_physical} file lines)",
            f"Merged duplicates: {self.merged} | Superseded by newer facts: {self.superseded} | Flagged for review: {self.flagged_for_review} | Passes: {self.passes}",
        ]
        lines += [f"Guard: {note}" for note in self.guard_notes]
        lines += [f"Warning: {note}" for note in self.warnings]
        lines.append(
            f"Result: {'under' if self.under_limit else 'STILL OVER'} the limit of {RESULT_LINE_LIMIT} file lines."
        )
        return "\n".join(lines)


def split_memory(text: str) -> Tuple[List[str], List[str]]:
    """Split MEMORY.md into (fact bullet lines, resolved-conflict lines).

    Bullets under '## Resolved conflicts' are conflict-log entries, every other bullet is a fact."""
    facts: List[str] = []
    conflicts: List[str] = []
    in_conflicts = False
    flags = comment_flags(text)
    for line, is_comment in zip(text.splitlines(), flags):
        stripped = line.strip()
        if is_comment or not stripped:
            continue
        if stripped.startswith("#"):
            in_conflicts = stripped.lower().startswith(CONFLICTS_HEADING.lower())
            continue
        if stripped.startswith("- "):
            (conflicts if in_conflicts else facts).append(line.rstrip())
    return facts, conflicts


def parse_facts(fact_lines: Sequence[str]) -> List[Fact]:
    """Parse bullet lines into Fact objects numbered L1..Ln in file order."""
    parsed: List[Fact] = []
    for index, line in enumerate(fact_lines, start=1):
        match = FACT_PATTERN.match(line.strip())
        if not match:
            continue
        date, body = match.group(1) or "", match.group(2)
        audit_match = re.search(r"<!--(.*?)-->", body)
        audit = audit_match.group(1).strip() if audit_match else ""
        body = INLINE_COMMENT.sub("", body).strip()
        critical = "[critical]" in body.lower()
        body = re.sub(r"\[critical\]\s*", "", body, flags=re.I).strip()
        parsed.append(Fact(index, date, body, critical, audit))
    return parsed


def fact_text(fact: Fact) -> str:
    """Render a fact back into 'L<n>: [date] text' form for the model."""
    return f"L{fact.line_no}: [{fact.date or 'undated'}] {'[critical] ' if fact.critical else ''}{fact.text}"


def render_fact(fact: Fact, extra_audit: Sequence[str] = ()) -> str:
    """Render one fact as a MEMORY.md bullet, with an audit comment listing merged lines."""
    audit = " ".join(part for part in [fact.audit, *extra_audit] if part)
    bullet = f"- [{fact.date}] " if fact.date else "- "
    bullet += ("[critical] " if fact.critical else "") + fact.text
    return bullet + (f" <!-- {audit} -->" if audit else "")


STOPWORDS = frozenset(
    "a an the is are was were be been of to in on at and or for with by as it its this that these those from my your their "
    "every each all any one also only use".split()
)
MIN_SHARED_WORDS = 2  # two lines can only be duplicates or contradictions when they share at least this many content words
MIN_MERGE_OVERLAP = 0.25  # shared words / words in the shorter line, for merges


def content_words(text: str) -> set:
    """Return the lower-case content words of a text (plural 's' removed, stop words dropped)."""
    words = set()
    for word in re.findall(r"[a-z0-9_]+(?::[a-z0-9_]+)*", re.sub(r"'s\b", "", text.lower())):
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if len(word) > 1 and word not in STOPWORDS:
            words.add(word)
    return words


def related(first: str, second: str) -> bool:
    """Return True when two fact texts share enough content words to be about the same thing."""
    return len(content_words(first) & content_words(second)) >= MIN_SHARED_WORDS


def locate_line(number: Any, quote: Any, by_line: Dict[int, Fact], warnings: List[str]) -> Optional[int]:
    """Find the fact a decision means. The quote (words copied from the line) wins over a wrong line number."""
    quote_words = content_words(re.sub(r"\[[^\]]*\]", " ", str(quote))) if quote else set()  # drop [date] / [critical] tags
    if not quote_words:  # no usable quote: trust the number
        return number if number in by_line else None
    # tolerate small copying slips in the quote: 80% of its words must appear in the line
    matches = [f.line_no for f in by_line.values() if len(quote_words & content_words(f.text)) >= 0.8 * len(quote_words)]
    if number in matches:
        return number
    if len(matches) == 1:
        warnings.append(f"decision said L{number} but its quote only fits L{matches[0]}; used L{matches[0]}")
        return matches[0]
    return None


def resolve_decisions(
    facts: Sequence[Fact], decisions: Sequence[Dict[str, Any]]
) -> Tuple[Dict[int, Dict[str, Any]], List[str], List[str]]:
    """Validate the model's decisions. Every fact is kept unless a valid decision says otherwise,
    so nothing can be dropped silently. Returns (decision by line, guard notes, warnings).

    A decision is ignored (the fact stays) when its line numbers or quotes do not point at two
    different facts, when the two facts share too few words to be about the same thing, or when a
    supersede would let an older fact replace a newer one."""
    by_line = {f.line_no: f for f in facts}
    accepted: Dict[int, Dict[str, Any]] = {}
    guard_notes: List[str] = []
    warnings: List[str] = []
    for decision in decisions:
        action = decision.get("action")
        line = locate_line(decision.get("line"), decision.get("line_quote"), by_line, warnings)
        target = locate_line(decision.get("target"), decision.get("target_quote"), by_line, warnings)
        if line is None or target is None or line == target or action not in ("merge", "supersede", "review"):
            warnings.append(f"ignored invalid decision {decision}")
            continue
        if not related(by_line[line].text, by_line[target].text):
            warnings.append(f"ignored {action} L{line} -> L{target}: the two lines are about different things")
            continue
        if action == "merge" and len(content_words(by_line[line].text) & content_words(by_line[target].text)) / max(
            1, min(len(content_words(by_line[line].text)), len(content_words(by_line[target].text)))
        ) < MIN_MERGE_OVERLAP:
            warnings.append(f"ignored merge L{line} -> L{target}: the lines are not duplicates (too little overlap)")
            continue
        if action == "supersede" and by_line[line].date and by_line[target].date and by_line[target].date < by_line[line].date:
            warnings.append(f"ignored supersede L{line} -> L{target}: the replacing line is older")
            continue
        if line in accepted:
            continue
        accepted[line] = {"action": action, "target": target, "reason": str(decision.get("reason", "")).strip()}

    # Guard 1: a [critical] fact never leaves '## Facts' because of supersede or review. Keep it and flag the other line.
    for line, dec in list(accepted.items()):
        if dec["action"] in ("supersede", "review") and by_line[line].critical:
            accepted.pop(line)
            target = dec["target"]
            if by_line[target].critical:
                guard_notes.append(f"L{line} and L{target} are both [critical]; both kept, the proposal to remove L{line} was ignored")
                continue
            guard_notes.append(
                f"L{line} is [critical]; the proposal to {dec['action']} it with L{target} was reversed, L{target} flagged for review"
            )
            accepted[target] = {
                "action": "review",
                "target": line,
                "reason": f"contradicts [critical] fact L{line}; " + dec["reason"],
            }

    # Targets must stay kept (not themselves removed). Follow chains of merges; drop broken ones.
    def final_target(start: int, seen: Optional[set] = None) -> Optional[int]:
        seen = seen or set()
        current = start
        while current in accepted and accepted[current]["action"] in ("merge",):
            if current in seen:
                return None
            seen.add(current)
            current = accepted[current]["target"]
        return None if current in accepted and accepted[current]["action"] != "review" else current

    for line, dec in list(accepted.items()):
        if line not in accepted:
            continue
        resolved = final_target(dec["target"])
        if resolved is None or resolved == line:
            warnings.append(f"L{line}: target L{dec['target']} is not a kept fact; L{line} kept")
            accepted.pop(line)
        else:
            dec["target"] = resolved

    # Guard 2: if the model flags BOTH lines of a pair for review, it could not decide: keep both and log one conflict.
    for line, dec in list(accepted.items()):
        other = accepted.get(dec["target"])
        if dec["action"] == "review" and other and other["action"] == "review" and other["target"] == line:
            reason = dec["reason"] or other["reason"] or "the model could not tell which is right"
            accepted[line] = {"action": "conflict", "target": dec["target"], "reason": reason}
            accepted[dec["target"]] = {"action": "conflict", "target": line, "reason": reason}
            guard_notes.append(f"L{line} and L{dec['target']} were each flagged against the other; both kept, one conflict logged")
    return accepted, guard_notes, warnings


def render_memory(
    facts: Sequence[Fact],
    decisions: Dict[int, Dict[str, Any]],
    old_conflicts: Sequence[str],
    moment: datetime,
) -> Tuple[str, Dict[str, int]]:
    """Build the consolidated MEMORY.md text from the facts and validated decisions."""
    by_line = {f.line_no: f for f in facts}
    merged_into: Dict[int, List[int]] = {}
    for line, dec in decisions.items():
        if dec["action"] == "merge":
            merged_into.setdefault(dec["target"], []).append(line)
    kept_lines: List[str] = []
    conflict_lines: List[str] = list(old_conflicts)
    counts = {"merged": 0, "superseded": 0, "review": 0, "kept": 0}
    for fact in facts:
        dec = decisions.get(fact.line_no)
        if dec and dec["action"] == "merge":
            counts["merged"] += 1
            continue
        if dec and dec["action"] == "supersede":
            winner = by_line[dec["target"]]
            counts["superseded"] += 1
            conflict_lines.append(
                f"- KEPT [{winner.date}] {winner.text} | SUPERSEDED [{fact.date}] {fact.text} | reason: {dec['reason'] or 'newer fact replaces it'}"
            )
            continue
        if dec and dec["action"] == "review":
            other = by_line[dec["target"]]
            counts["review"] += 1
            conflict_lines.append(
                f"- NEEDS REVIEW (kept: [{other.date}] {other.text}) | UNVERIFIED [{fact.date}] {fact.text} | reason: {dec['reason'] or 'cannot tell which is right'}"
            )
            continue
        extras: List[str] = []
        if dec and dec["action"] == "conflict":
            other = by_line[dec["target"]]
            extras.append(f"CONFLICT with the [{other.date}] line, needs review")
            if fact.line_no < other.line_no:
                counts["review"] += 1
                conflict_lines.append(
                    f"- UNRESOLVED (both kept in Facts) [{fact.date}] {fact.text} | [{other.date}] {other.text} | reason: {dec['reason']}"
                )
        if fact.line_no in merged_into:
            refs = ", ".join(f"L{n}" for n in merged_into[fact.line_no])
            extras.append(f"merged duplicates {refs}")
            if any(by_line[n].critical for n in merged_into[fact.line_no]):
                fact = Fact(fact.line_no, fact.date, fact.text, True, fact.audit)
        counts["kept"] += 1
        kept_lines.append(render_fact(fact, extras))

    out = ["# MEMORY.md", f"<!-- last-consolidated: {format_timestamp(moment)} -->", FORMAT_HINT, FACTS_HEADING, *kept_lines]
    if conflict_lines:
        out += ["", CONFLICTS_HEADING, *conflict_lines]
    return "\n".join(out) + "\n", counts


def consolidate_text(
    text: str,
    model: Any,
    now: Optional[datetime] = None,
    max_passes: int = 3,
) -> Tuple[str, ConsolidationReport]:
    """Consolidate MEMORY.md text with the model's help and return (new text, report).

    The model only PROPOSES merge/supersede/review decisions. The code keeps every fact the model
    did not explicitly (and validly) handle, protects [critical] facts, writes superseded and
    doubtful facts into '## Resolved conflicts' instead of deleting them, and repeats once if the
    result is still too long."""
    now = now or datetime.now(timezone.utc)
    current = text
    fact_lines, old_conflicts = split_memory(current)
    before_facts = len(parse_facts(fact_lines))
    report = ConsolidationReport(
        before_lines=count_memory_lines(text),
        after_lines=0,
        before_physical=len(text.splitlines()),
        after_physical=0,
        before_facts=before_facts,
        after_facts=0,
        merged=0,
        superseded=0,
        flagged_for_review=0,
        passes=0,
    )
    result_text = text
    for _ in range(max_passes):
        fact_lines, old_conflicts = split_memory(current)
        facts = parse_facts(fact_lines)
        if not facts:
            break
        listing = "\n".join(fact_text(f) for f in facts)
        response = model.complete(
            [{"role": "system", "content": CONSOLIDATION_PROMPT}, {"role": "user", "content": listing}],
            response_format=CONSOLIDATION_SCHEMA,
        )
        try:
            proposed = json.loads(response.content).get("decisions", [])
        except (json.JSONDecodeError, AttributeError):
            report.warnings.append("model returned invalid JSON; no changes made in this pass")
            break
        report.proposed.append(list(proposed))
        accepted, guard_notes, warnings = resolve_decisions(facts, proposed)
        report.guard_notes += guard_notes
        report.warnings += warnings
        result_text, counts = render_memory(facts, accepted, old_conflicts, now)
        report.passes += 1
        report.merged += counts["merged"]
        report.superseded += counts["superseded"]
        report.flagged_for_review += counts["review"]
        current = result_text
        if len(result_text.splitlines()) < RESULT_LINE_LIMIT:
            break
    final_facts, _ = split_memory(result_text)
    report.after_facts = len(parse_facts(final_facts))
    report.after_lines = count_memory_lines(result_text)
    report.after_physical = len(result_text.splitlines())
    report.under_limit = report.after_physical < RESULT_LINE_LIMIT
    return result_text, report


def consolidate_file(
    path: Path | str, model: Any, now: Optional[datetime] = None, backup: bool = True
) -> ConsolidationReport:
    """Consolidate MEMORY.md on disk (keeping a MEMORY.md.bak copy) and return the report."""
    file = Path(path)
    original = file.read_text(encoding="utf-8")
    if backup:
        shutil.copyfile(file, file.with_name(file.name + ".bak"))
    new_text, report = consolidate_text(original, model, now)
    file.write_text(new_text, encoding="utf-8")
    return report


# --------------------------------------------------------------------------- /dream
def _normalize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def is_known_fact(candidate: str, known: Sequence[str], threshold: float = 0.8) -> bool:
    """Return True when a candidate fact is (almost) already in memory, by word overlap."""
    words = _normalize(candidate)
    if not words:
        return True
    for other in known:
        other_words = _normalize(other)
        if other_words and len(words & other_words) / len(words | other_words) >= threshold:
            return True
    return False


def dream(
    memory_path: Path | str,
    history: Sequence[Dict[str, str]],
    model: Any,
    now: Optional[datetime] = None,
    window: int = 12,
) -> List[str]:
    """Extract durable facts from the recent conversation and append them to MEMORY.md.

    Returns the list of bullet lines that were added."""
    now = now or datetime.now(timezone.utc)
    file = Path(memory_path)
    text = file.read_text(encoding="utf-8") if file.is_file() else "# MEMORY.md\n"
    recent = [m for m in history if m.get("role") in ("user", "assistant")][-window:]
    if not recent:
        return []
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    response = model.complete(
        [
            {"role": "system", "content": DREAM_PROMPT},
            {"role": "user", "content": f"MEMORY.md now:\n{strip_comments(text)}\n\nRecent conversation:\n{transcript}"},
        ],
        response_format=DREAM_SCHEMA,
    )
    try:
        candidates = json.loads(response.content).get("facts", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    known = [f.text for f in parse_facts(split_memory(text)[0])]
    added: List[str] = []
    for item in candidates:
        fact = str(item.get("fact", "")).strip()
        if not fact or is_known_fact(fact, known + [a for a in added]):
            continue
        tag = "[critical] " if item.get("critical") else ""
        added.append(f"- [{now.date().isoformat()}] {tag}{fact}")
    if not added:
        return []
    lines = text.rstrip("\n").splitlines()
    if FACTS_HEADING not in lines:
        lines += ["", FACTS_HEADING]
    # insert after the last fact bullet that precedes the conflicts section (or at the end of Facts)
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if line.strip().lower().startswith(CONFLICTS_HEADING.lower()):
            insert_at = i
            while insert_at > 0 and not lines[insert_at - 1].strip():
                insert_at -= 1
            break
    lines[insert_at:insert_at] = added
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return added


# --------------------------------------------------------------------------- session + commands
class FileMemorySession:
    """A chat session whose system prompt comes from AGENT.md and MEMORY.md."""

    def __init__(
        self,
        model: Any,
        agent_path: Path | str = AGENT_FILE,
        memory_path: Path | str = MEMORY_FILE,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.model = model
        self.agent_path = Path(agent_path)
        self.memory_path = Path(memory_path)
        self.clock = clock
        self.history: List[Dict[str, str]] = []

    # -- helpers
    def system_prompt(self) -> str:
        """Rebuild the system prompt from the two files (so /dream and /compact take effect at once)."""
        agent_text, memory_text = load_memory_files(self.agent_path, self.memory_path)
        return build_system_prompt(agent_text, memory_text)

    def status_line(self) -> str:
        """Describe the size and consolidation state of MEMORY.md in one line."""
        text = load_memory_md(self.memory_path)
        last = read_last_consolidated(text)
        reasons = consolidation_reasons(text, self.clock())
        return (
            f"MEMORY.md: {count_memory_lines(text)} memory lines (limit {MEMORY_LINE_LIMIT}), "
            f"last consolidated {format_timestamp(last) if last else 'never'}, "
            f"consolidation due: {'YES - ' + '; '.join(reasons) if reasons else 'no'}"
        )

    def startup_check(self) -> str:
        """Run at session start: consolidate automatically when MEMORY.md says it is due."""
        text = load_memory_md(self.memory_path)
        reasons = consolidation_reasons(text, self.clock())
        if not reasons:
            return "Memory check: " + self.status_line()
        report = consolidate_file(self.memory_path, self.model, self.clock())
        return "Memory check: consolidation was due (" + "; ".join(reasons) + ") - ran it automatically.\n" + report.summary()

    # -- commands
    def command_memory(self) -> str:
        """Show AGENT.md headings and the full MEMORY.md plus the consolidation status."""
        agent_text, memory_text = load_memory_files(self.agent_path, self.memory_path)
        headings = [line.strip() for line in agent_text.splitlines() if line.startswith("## ")]
        instructions = sum(1 for line in agent_text.splitlines() if re.match(r"^\s*(?:-|\d+\.)\s+\S", line))
        return (
            f"AGENT.md: {len(agent_text.splitlines())} lines, {instructions} instruction lines; sections: "
            f"{', '.join(h[3:] for h in headings) or '(none)'}\n"
            f"{self.status_line()}\n"
            f"----- MEMORY.md -----\n{memory_text.rstrip() or '(empty)'}"
        )

    def command_compact(self) -> str:
        """Consolidate MEMORY.md and report the counts before and after."""
        report = consolidate_file(self.memory_path, self.model, self.clock())
        return "/compact\n" + report.summary()

    def command_dream(self) -> str:
        """Add durable facts from the recent conversation to MEMORY.md."""
        added = dream(self.memory_path, self.history, self.model, self.clock())
        if not added:
            return "/dream: nothing new worth remembering in the recent conversation."
        return "/dream: added to MEMORY.md:\n" + "\n".join(added)

    def handle(self, text: str) -> str:
        """Handle one line of input: a slash command or a normal chat message."""
        stripped = text.strip()
        command = stripped.split()[0].lower() if stripped.startswith("/") else ""
        if command == "/help":
            return HELP_TEXT
        if command == "/memory":
            return self.command_memory()
        if command == "/compact":
            return self.command_compact()
        if command == "/dream":
            return self.command_dream()
        if command:
            return f"Unknown command {command}. Type /help for the list."
        self.history.append({"role": "user", "content": stripped})
        messages = [{"role": "system", "content": self.system_prompt()}, *self.history]
        response = self.model.complete(messages)
        reply = response.content.strip()
        self.history.append({"role": "assistant", "content": reply})
        return reply
