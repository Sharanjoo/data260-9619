"""Run: python scripts/test_file_memory_hw06.py
Offline tests for src/file_memory.py (fake model, temp files; no Ollama needed)."""
import json
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import file_memory as fm  # noqa: E402

ORIGINAL = (ROOT / "reports/hw06/MEMORY_original.md").read_text(encoding="utf-8")
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed += bool(cond)
    failed += (not cond)
    print(("PASS" if cond else "FAIL"), name, detail)


class FakeModel:
    """Returns canned JSON for consolidation/dream, a plain reply otherwise."""
    def __init__(self, decisions=None, dream_facts=None):
        self.decisions, self.dream_facts, self.calls = decisions or [], dream_facts or [], []
    def complete(self, messages, tools=None, *, temperature=0.0, response_format=None):
        self.calls.append(messages)
        system = messages[0]["content"]
        if system.startswith("You consolidate"):
            content = json.dumps({"decisions": self.decisions})
        elif system.startswith("You read a recent conversation"):
            content = json.dumps({"facts": self.dream_facts})
        else:
            content = "plain reply"
        return SimpleNamespace(content=content, input_tokens=1, output_tokens=1)


def line_of(text, needle):
    for i, line in enumerate(text.splitlines(), start=1):
        if needle.lower() in line.lower():
            return i
    raise KeyError(needle)


def facts_section(text):
    return fm.split_memory(text)[0]


# ---- counting + comments -----------------------------------------------------------
sample = "# T\n<!-- c1 -->\n<!--\nmulti\nline\n-->\n\n- a\n- b <!-- inline -->\n## H\n"
check("count: headings+bullets count, comments and blanks do not", fm.count_memory_lines(sample) == 4, str(fm.memory_lines(sample)))
check("original has 55 file lines and 50 facts", len(ORIGINAL.splitlines()) == 55 and len(fm.parse_facts(facts_section(ORIGINAL))) == 50)
check("original has >40 memory lines", fm.count_memory_lines(ORIGINAL) == 52, str(fm.count_memory_lines(ORIGINAL)))
check("strip_comments removes inline + block comments", "<!--" not in fm.strip_comments(sample))

# ---- timestamp + trigger -----------------------------------------------------------
check("read_last_consolidated parses Z time", fm.read_last_consolidated(ORIGINAL) == datetime(2026, 10, 1, tzinfo=timezone.utc))
check("read_last_consolidated handles format-hint pipe", fm.read_last_consolidated("<!-- last-consolidated: 2026-10-02T03:04:05Z | x -->") is not None)
check("missing timestamp -> None", fm.read_last_consolidated("# x\n- a\n") is None)
small_fresh = fm.stamp_consolidated("# MEMORY.md\n- [2026-10-16] a fact\n", NOW - timedelta(hours=2))
check("not due: few lines, 2 h old", not fm.needs_consolidation(small_fresh, NOW), str(fm.consolidation_reasons(small_fresh, NOW)))
small_old = fm.stamp_consolidated("# MEMORY.md\n- [2026-10-16] a fact\n", NOW - timedelta(hours=25))
check("due: older than 24 h", fm.needs_consolidation(small_old, NOW) and "hours ago" in fm.consolidation_reasons(small_old, NOW)[0])
edge = fm.stamp_consolidated("# MEMORY.md\n- [2026-10-16] a fact\n", NOW - timedelta(hours=24))
check("exactly 24 h is NOT yet due", not fm.needs_consolidation(edge, NOW))
many = fm.stamp_consolidated("# MEMORY.md\n" + "".join(f"- [2026-10-16] fact {i}\n" for i in range(41)), NOW)
check("due: 42 memory lines (heading + 41 bullets) is > 40", fm.count_memory_lines(many) == 42 and "memory lines" in fm.consolidation_reasons(many, NOW)[0])
forty = fm.stamp_consolidated("".join(f"- [2026-10-16] fact {i}\n" for i in range(40)), NOW)
check("exactly 40 lines is NOT due", fm.count_memory_lines(forty) == 40 and not fm.needs_consolidation(forty, NOW))
check("no timestamp but facts -> due", fm.needs_consolidation("# M\n- a\n", NOW))
check("stamp replaces existing stamp (only one)", fm.stamp_consolidated(ORIGINAL, NOW).count("last-consolidated") == 1 and fm.read_last_consolidated(fm.stamp_consolidated(ORIGINAL, NOW)) == NOW)

# ---- system prompt -----------------------------------------------------------------
prompt = fm.build_system_prompt("# AGENT\n- rule one <!-- hidden -->\n", ORIGINAL)
check("system prompt has both files, no comments", "rule one" in prompt and "Oakland" in prompt and "<!--" not in prompt and "AGENT.md" in prompt and "MEMORY.md" in prompt)

# ---- consolidation with a model that behaves like a good reviewer --------------------
def ln(needle):
    facts = fm.parse_facts(facts_section(ORIGINAL))
    for f in facts:
        if needle.lower() in f.text.lower():
            return f.line_no
    raise KeyError(needle)

def group(key):
    return [f.line_no for f in fm.parse_facts(facts_section(ORIGINAL)) if key.lower() in f.text.lower()]

good = []
for key in ["qwen3:8b", "DOMAIN_ID 3", "git commands", "Times New Roman", "terminal screenshot"]:
    lines = group(key)
    keeper = lines[-1]
    good += [{"line": n, "action": "merge", "target": keeper, "reason": "paraphrase"} for n in lines[:-1]]
good += [
    {"line": ln("San Jose"), "action": "supersede", "target": ln("lives in Oakland"), "reason": "newer address"},
    {"line": ln("daily email"), "action": "supersede", "target": ln("weekly email"), "reason": "newer preference"},
    {"line": ln("port 8000"), "action": "supersede", "target": ln("port 8619"), "reason": "newer port"},
    {"line": ln("not allergic"), "action": "review", "target": ln("severe peanut"), "reason": "joke, unverified"},
]
text, rep = fm.consolidate_text(ORIGINAL, FakeModel(good), NOW)
check("good model: under 40 file lines", rep.under_limit and len(text.splitlines()) < 40, f"{len(text.splitlines())} lines")
check("good model: 5 dup groups merged to one line each", all(sum(1 for l in facts_section(text) if k.lower() in l.lower()) == 1 for k in ["qwen3:8b", "DOMAIN_ID 3", "git commands", "Times New Roman", "terminal screenshot"]))
check("good model: counts (18 merged, 3 superseded, 1 review)", (rep.merged, rep.superseded, rep.flagged_for_review) == (18, 3, 1), str((rep.merged, rep.superseded, rep.flagged_for_review)))
check("good model: keepers in Facts, losers only in conflicts", all(
    any(k.lower() in l.lower() for l in facts_section(text)) and not any(x.lower() in l.lower() for l in facts_section(text))
    and any(x.lower() in l.lower() for l in fm.split_memory(text)[1])
    for k, x in [("lives in Oakland", "lives in San Jose"), ("weekly email digest", "daily email digest"), ("port 8619", "port 8000"), ("severe peanut allergy", "not allergic to peanuts")]))
check("good model: all 19 unique facts survive", sum(1 for f in fm.parse_facts(facts_section(text))) == 28)
check("good model: stamped now", fm.read_last_consolidated(text) == NOW)
check("good model: critical tag preserved", any("[critical]" in l and "peanut allergy" in l for l in facts_section(text)))
check("good model: audit comments kept for merges", "merged duplicates" in text)
check("good model: consolidated file is no longer due", not fm.needs_consolidation(text, NOW + timedelta(hours=1)))

# ---- a model that gets the trap WRONG: the guard must protect the critical fact ------
bad = list(good)
bad = [d for d in bad if d["line"] != ln("not allergic")] + [
    {"line": ln("severe peanut"), "action": "supersede", "target": ln("not allergic"), "reason": "newest wins"}]
text2, rep2 = fm.consolidate_text(ORIGINAL, FakeModel(bad), NOW)
check("guard: critical allergy NOT superseded", any("severe peanut allergy" in l for l in facts_section(text2)) and rep2.guard_notes, str(rep2.guard_notes))
check("guard: the joking claim is flagged for review, not silently dropped", any("not allergic to peanuts" in l and "NEEDS REVIEW" in l for l in fm.split_memory(text2)[1]))

# ---- a lazy / empty model: nothing may be deleted ----------------------------------
text3, rep3 = fm.consolidate_text(ORIGINAL, FakeModel([]), NOW, max_passes=1)
check("empty decisions: every fact kept (no silent deletion)", rep3.after_facts == 50 and not rep3.under_limit)
check("empty decisions: reported as STILL OVER", "STILL OVER" in rep3.summary())
junk = [{"line": 999, "action": "merge", "target": 1, "reason": ""}, {"line": 3, "action": "merge", "target": 3, "reason": ""},
        {"line": 5, "action": "merge", "target": 6, "reason": ""}, {"line": 6, "action": "supersede", "target": 5, "reason": ""}]
text4, rep4 = fm.consolidate_text(ORIGINAL, FakeModel(junk), NOW, max_passes=1)
check("invalid / circular decisions are ignored with warnings", rep4.after_facts >= 49 and rep4.warnings, str(rep4.warnings[:2]))
check("model returning invalid JSON changes nothing", fm.consolidate_text(ORIGINAL, SimpleNamespace(complete=lambda *a, **k: SimpleNamespace(content="not json")), NOW)[1].passes == 0)

# ---- second pass finishes the job ----------------------------------------------------
class TwoPass(FakeModel):
    def __init__(self):
        super().__init__([])
        self.n = 0
    def complete(self, messages, tools=None, *, temperature=0.0, response_format=None):
        self.n += 1
        if messages[0]["content"].startswith("You consolidate") and self.n == 1:
            self.decisions = [d for d in good if d["action"] == "supersede" or d["action"] == "review"]
        elif messages[0]["content"].startswith("You consolidate"):
            facts = fm.parse_facts([l for l in messages[1]["content"].splitlines()])  # not used
            self.decisions = []
            for key in ["qwen3:8b", "DOMAIN_ID 3", "git commands", "Times New Roman", "terminal screenshot"]:
                nums = [int(m.group(1)) for m in re.finditer(rf"^L(\d+): .*{re.escape(key)}", messages[1]["content"], re.M | re.I)]
                self.decisions += [{"line": n, "action": "merge", "target": nums[-1], "reason": "dup"} for n in nums[:-1]]
        return super().complete(messages, tools, temperature=temperature, response_format=response_format)
text5, rep5 = fm.consolidate_text(ORIGINAL, TwoPass(), NOW)
check("two passes: reaches < 40 lines, keeps pass-1 conflict log", rep5.passes == 2 and rep5.under_limit and len(fm.split_memory(text5)[1]) == 4, f"{len(text5.splitlines())} lines, passes {rep5.passes}")

# ---- failure modes seen with the real model (qwen3:8b): the guards must stop them ----------
def run_decisions(decisions, text=ORIGINAL):
    return fm.consolidate_text(text, FakeModel(decisions), NOW, max_passes=1)

t6, r6 = run_decisions([{"line": ln("SID4 is 9619"), "action": "merge", "target": ln("qwen3:8b via Ollama is the chat model"), "reason": "same"}])
check("guard: merge of two unrelated facts is refused and both kept",
      any("about different things" in w for w in r6.warnings) and any("SID4 is 9619" in l for l in facts_section(t6)) and r6.merged == 0, str(r6.warnings[:1]))

t7, r7 = run_decisions([{"line": ln("laptop is an HP Pavilion"), "action": "review", "target": ln("lives in Oakland"), "reason": "location"}])
check("guard: review of a fact against an unrelated fact is refused (HP laptop stays in Facts)",
      any("HP Pavilion" in l for l in facts_section(t7)) and not fm.split_memory(t7)[1], str(r7.warnings[:1]))

t8, r8 = run_decisions([{"line": 999, "line_quote": "peanut allergy confirmed doctor", "action": "review", "target": ln("not allergic"), "target_quote": "not allergic peanuts joking", "reason": "x"}])
check("quote wins over a wrong line number (critical line is not moved out)", any("used L" in w for w in r8.warnings) and r8.guard_notes and any("severe peanut allergy" in l for l in facts_section(t8)), str(r8.warnings[:1]))

mutual = [
    {"line": ln("not allergic"), "action": "review", "target": ln("severe peanut"), "reason": "newer is unverified"},
    {"line": ln("severe peanut"), "action": "review", "target": ln("not allergic"), "reason": "contradictory"},
]
t9, r9 = run_decisions(mutual)
check("guard: model flags both allergy lines against each other -> [critical] stays in Facts, joke is logged",
      any("severe peanut allergy" in l for l in facts_section(t9)) and not any("not allergic" in l for l in facts_section(t9))
      and any("not allergic" in l and "NEEDS REVIEW" in l for l in fm.split_memory(t9)[1]) and r9.guard_notes, str(r9.guard_notes))

mutual2 = [
    {"line": ln("lives in San Jose"), "action": "review", "target": ln("lives in Oakland"), "reason": "unverified"},
    {"line": ln("lives in Oakland"), "action": "review", "target": ln("lives in San Jose"), "reason": "unverified"},
]
t10, r10 = run_decisions(mutual2)
unresolved = [l for l in fm.split_memory(t10)[1] if "UNRESOLVED" in l]
check("guard: mutual review of two ordinary facts keeps BOTH in Facts and logs one UNRESOLVED conflict",
      any("lives in Oakland" in l for l in facts_section(t10)) and any("lives in San Jose" in l for l in facts_section(t10)) and len(unresolved) == 1
      and any("CONFLICT" in l for l in facts_section(t10)), str(unresolved))

t11, r11 = run_decisions([{"line": ln("lives in Oakland"), "action": "supersede", "target": ln("lives in San Jose"), "reason": "x"}])
check("guard: an older fact cannot supersede a newer one", any("older" in w for w in r11.warnings) and any("lives in Oakland" in l for l in facts_section(t11)) and r11.superseded == 0)

t12, r12 = run_decisions([{"line": 5, "action": "merge", "target": 5, "reason": "x"}])
check("guard: a decision whose line equals its target is ignored", r12.merged == 0 and r12.warnings)

# ---- second real run (qwen3:8b): more guard cases -------------------------------------------
t13, r13 = run_decisions([{"line": ln("toddler drinks oat milk"), "action": "merge", "target": ln("partner is lactose intolerant"), "reason": "same"}])
check("guard: possessive 's does not make 'toddler / oat milk' a duplicate of 'partner / lactose' (both kept)",
      r13.merged == 0 and any("oat milk" in l for l in facts_section(t13)), str(r13.warnings[:1]))

t14, r14 = run_decisions([{"line": ln("One FastAPI app serves every homework"), "action": "merge", "target": ln("qwen3:8b via Ollama is the chat model"), "reason": "same"}])
check("guard: a shared generic word like 'every homework' does not make two facts duplicates", r14.merged == 0 and any("MySQL holds" in l for l in facts_section(t14)), str(r14.warnings[:1]))

t15, r15 = run_decisions([
    {"line": ln("severe peanut"), "line_quote": "[critical] The user has a severe peanut allergy (confirmed by a doctr).", "action": "review",
     "target": ln("not allergic"), "target_quote": "The user said they are not allergic to peanuts (joking, unverified).", "reason": "x"}])
check("quote tolerates the [critical] tag and a typo, so the guard still sees the critical line",
      r15.guard_notes and any("severe peanut allergy" in l for l in facts_section(t15)) and any("not allergic" in l and "NEEDS REVIEW" in l for l in fm.split_memory(t15)[1]), str(r15.guard_notes or r15.warnings[:1]))

# ---- files + commands -----------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / "AGENT.md").write_text("# AGENT\n## Coding conventions\n- one\n- two\n", encoding="utf-8")
    (tmp / "MEMORY.md").write_text(ORIGINAL, encoding="utf-8")
    model = FakeModel(good, [{"fact": "The user wants the demo on Friday.", "critical": False}, {"fact": "The user lives in Oakland.", "critical": False}])
    session = fm.FileMemorySession(model, tmp / "AGENT.md", tmp / "MEMORY.md", clock=lambda: NOW)
    check("/help lists the four commands", all(c in session.handle("/help") for c in ["/memory", "/compact", "/dream", "/help"]))
    mem = session.handle("/memory")
    check("/memory shows AGENT.md summary, status and MEMORY.md", "Coding conventions" in mem and "consolidation due: YES" in mem and "Oakland" in mem)
    reply = session.handle("hello there")
    check("chat sends AGENT.md + MEMORY.md in the system prompt", reply == "plain reply" and "Oakland" in model.calls[-1][0]["content"] and "Coding conventions" in model.calls[-1][0]["content"])
    before = (tmp / "MEMORY.md").read_text(encoding="utf-8")
    out = session.handle("/compact")
    after = (tmp / "MEMORY.md").read_text(encoding="utf-8")
    check("/compact reports before and after counts", "Before: 52 memory lines" in out and re.search(r"After:\s+\d+ memory lines", out) and "under the limit" in out, out.splitlines()[1] if len(out.splitlines()) > 1 else out)
    check("/compact rewrote MEMORY.md and kept a .bak", after != before and (tmp / "MEMORY.md.bak").read_text(encoding="utf-8") == before)
    dreamed = session.handle("/dream")
    check("/dream adds new durable fact, skips known one", "demo on Friday" in dreamed and "Oakland" not in dreamed.split("added to MEMORY.md:")[-1], dreamed)
    final = (tmp / "MEMORY.md").read_text(encoding="utf-8")
    facts_before_conflicts = final.split(fm.CONFLICTS_HEADING)[0]
    check("/dream inserts the fact inside ## Facts", "demo on Friday" in facts_before_conflicts)
    check("unknown command is reported", "Unknown command" in session.handle("/nope"))
    empty = fm.FileMemorySession(FakeModel(), tmp / "AGENT.md", tmp / "NEW.md", clock=lambda: NOW)
    check("/dream with no conversation does nothing", "nothing new" in empty.handle("/dream"))
    # startup check: due -> auto-consolidates; not due -> just reports
    (tmp / "MEMORY.md").write_text(ORIGINAL, encoding="utf-8")
    s2 = fm.FileMemorySession(FakeModel(good), tmp / "AGENT.md", tmp / "MEMORY.md", clock=lambda: NOW)
    msg = s2.startup_check()
    check("startup check auto-consolidates when due", "ran it automatically" in msg and fm.count_memory_lines((tmp / "MEMORY.md").read_text(encoding="utf-8")) < 40)
    check("startup check is quiet when not due", "ran it automatically" not in fm.FileMemorySession(FakeModel(good), tmp / "AGENT.md", tmp / "MEMORY.md", clock=lambda: NOW + timedelta(hours=1)).startup_check())
    # persistence after a "restart": a brand-new session object sees the dreamed fact
    s3 = fm.FileMemorySession(FakeModel(), tmp / "AGENT.md", tmp / "MEMORY.md", clock=lambda: NOW)
    check("persistence: a new session reads the same MEMORY.md", "Oakland" in s3.system_prompt())

print(f"\n{passed}/{passed + failed} checks passed")
sys.exit(1 if failed else 0)
