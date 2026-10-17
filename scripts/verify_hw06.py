"""HW6 self-check (make verify-hw06): a smoke test of the running system plus the required deliverables.

It checks that the FastAPI backend answers on PORT_BASE, that the MongoDB document API (Part 1) and the memory
endpoints (Part 2, including POST /api/chat) work, that the Part 3 probes/raw data/metrics exist, and that the
Part 4 file-memory pieces behave (AGENT.md, 55-line MEMORY.md, consolidation, commands, AGENT.md compliance).
It writes reports/hw06/verification.json.

Needs: docker compose up -d, Ollama running with qwen3:8b + nomic-embed-text, and
pip install requests pyyaml pymongo mongomock. It does NOT modify application code: it hashes code/ and src/
before and after and records the result as one of the checks. Temporary data it creates (one recall notice, one
verification user's chat history) is deleted again.

Usage (repo root):
    python scripts/verify_hw06.py
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw06"
RAW = REPORT_DIR / "raw"
sys.path.insert(0, str(REPO_ROOT))

BASE_URL = "http://localhost:8619"
OLLAMA_URL = "http://localhost:11434"
MONGO_URI = "mongodb://localhost:27017"
HOMEWORK_NUMBER = 6
SID4 = 9619
PORT_BASE = 8619
SEED = 9619
VERIFY_SEED = 269619
MODEL_CONFIG = ("qwen3:8b via Ollama (temperature 0, think=False) + nomic-embed-text embeddings; MongoDB 7 (s9619_doc); "
                "SHORT_TERM_N sweep 4/12/30 + compress_old_assistant policy; file memory AGENT.md + MEMORY.md")
CHAT_TIMEOUT_S = 1200
SETTINGS = ["N4", "N12", "N30", "POLICY"]

checks: list[dict] = []
info: dict = {}


def record(name: str, passed: bool, detail: str = "") -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown (not a git checkout, or git unavailable)"


def tree_hash(*folders: str) -> str:
    digest = hashlib.sha256()
    for folder in folders:
        for path in sorted((REPO_ROOT / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                digest.update(str(path.relative_to(REPO_ROOT)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---------------------------------------------------------------- Part 1 + backend
def check_backend() -> None:
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        record("backend_responds_on_port_base", r.status_code == 200 and r.json().get("port") == PORT_BASE,
               f"GET /api/health -> {r.status_code} {r.text[:60]}")
    except requests.RequestException as exc:
        record("backend_responds_on_port_base", False, f"{type(exc).__name__} on {BASE_URL} -- is docker compose up?")


def check_part1(rng: random.Random) -> None:
    url = f"{BASE_URL}/api/hw6/notices"
    categories = ["food-safety-recall", "allergen-alert", "quality-withdrawal", "supply-shortage"]
    body = {"title": f"verify-hw06 notice {VERIFY_SEED}", "description": "temporary record created by verify_hw06.py",
            "status": "open", "category": rng.choice(categories), "notice_date": "2026-10-05T09:30:00Z"}
    try:
        created = requests.post(url, json=body, timeout=15)
        nid = created.json().get("id", "") if created.status_code == 201 else ""
        got = requests.get(f"{url}/{nid}", timeout=15)
        put = requests.put(f"{url}/{nid}", json={**body, "status": "investigating"}, timeout=15)
        deleted = requests.delete(f"{url}/{nid}", timeout=15)
        gone = requests.get(f"{url}/{nid}", timeout=15)
        codes = [created.status_code, got.status_code, put.status_code, deleted.status_code, gone.status_code]
        record("part1_notice_crud_roundtrip", codes == [201, 200, 200, 200, 404] and put.json().get("status") == "investigating",
               f"POST/GET/PUT/DELETE/GET-after -> {codes} (expected [201, 200, 200, 200, 404])")
    except (requests.RequestException, ValueError) as exc:
        record("part1_notice_crud_roundtrip", False, f"{type(exc).__name__}: {exc}")
    try:
        bad = {
            "missing_title": {k: v for k, v in body.items() if k != "title"},
            "bad_enum": {**body, "status": "closed"},
            "title_101_chars": {**body, "title": "x" * 101},
            "wrong_type": {**body, "title": 123},
        }
        codes = {name: requests.post(url, json=payload, timeout=15).status_code for name, payload in bad.items()}
        record("part1_validation_rejects_invalid_data", all(c == 422 for c in codes.values()), f"{codes} (expected all 422)")
    except requests.RequestException as exc:
        record("part1_validation_rejects_invalid_data", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- Part 2
def check_part2(rng: random.Random) -> str:
    user = f"verify-{VERIFY_SEED}-{int(time.time())}"
    messages = ["Hi, I am allergic to peanuts.", "Please remember that I shop at Safeway.", "I live in Oakland."]
    text = rng.choice(messages)
    try:
        r = requests.post(f"{BASE_URL}/api/chat", json={"user_id": user, "message": text}, timeout=CHAT_TIMEOUT_S)
        data = r.json()
        used = data.get("memory_used", {})
        ok = (r.status_code == 200 and isinstance(data.get("reply"), str) and data["reply"].strip() != ""
              and {"short_term", "long_term", "episodic"} <= set(used) and used["short_term"]["count"] >= 1
              and data.get("metrics", {}).get("prompt_tokens", 0) > 0)
        record("part2_post_api_chat_returns_reply", ok,
               f"HTTP {r.status_code}, reply length {len(data.get('reply', ''))}, prompt_tokens={data.get('metrics', {}).get('prompt_tokens')}, "
               f"memory_used keys={sorted(used)}")
    except (requests.RequestException, ValueError) as exc:
        record("part2_post_api_chat_returns_reply", False, f"{type(exc).__name__}: {exc}")
    try:
        r = requests.get(f"{BASE_URL}/api/memory/{user}", timeout=30)
        m = r.json()
        record("part2_get_memory_returns_messages", r.status_code == 200 and len(m.get("messages", [])) >= 2
               and {"session_summary", "lifetime_summary", "episodes"} <= set(m),
               f"HTTP {r.status_code}, {len(m.get('messages', []))} messages, keys={sorted(m)}")
    except (requests.RequestException, ValueError) as exc:
        record("part2_get_memory_returns_messages", False, f"{type(exc).__name__}: {exc}")
    try:
        r = requests.get(f"{BASE_URL}/api/aggregate/{user}", timeout=30)
        a = r.json()
        record("part2_get_aggregate_counts_by_date", r.status_code == 200 and a.get("total_messages", 0) >= 2
               and isinstance(a.get("daily_message_counts"), list) and a["daily_message_counts"],
               f"HTTP {r.status_code}, total_messages={a.get('total_messages')}, days={len(a.get('daily_message_counts', []))}")
    except (requests.RequestException, ValueError) as exc:
        record("part2_get_aggregate_counts_by_date", False, f"{type(exc).__name__}: {exc}")
    try:
        r = requests.get(f"{BASE_URL}/api/memory-config", timeout=15)
        info["server_config"] = r.json()
    except (requests.RequestException, ValueError):
        info["server_config"] = None
    return user


def check_mongo_collections(user: str) -> None:
    try:
        from pymongo import MongoClient

        db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)["s9619_doc"]
        names = set(db.list_collection_names())
        needed = {"recall_notices", "messages", "summaries", "episodes"}
        record("part2_mongo_collections_exist_in_s9619_doc", needed <= names, f"found {sorted(names)}")
        for col in ("messages", "summaries", "episodes"):  # remove the verification user's temporary data
            db[col].delete_many({"user_id": user})
    except Exception as exc:  # noqa: BLE001
        record("part2_mongo_collections_exist_in_s9619_doc", False, f"{type(exc).__name__}: {exc} (pip install pymongo; is mongo up on 27017?)")


# ---------------------------------------------------------------- Part 3
def check_part3() -> None:
    try:
        cfg = yaml.safe_load((REPORT_DIR / "memory_probes.yaml").read_text(encoding="utf-8"))
        probes = cfg["probes"]
        ok = len(probes) == 5 and all(p.get("question") and p.get("expected") and p.get("required_groups") for p in probes) \
            and sorted(cfg["rubric"]) == [1, 2, 3, 4, 5]
        record("part3_memory_probes_yaml_valid", ok, f"{len(probes)} probes, rubric levels {sorted(cfg['rubric'])}")
    except Exception as exc:  # noqa: BLE001
        record("part3_memory_probes_yaml_valid", False, f"{type(exc).__name__}: {exc}")
    try:
        import csv

        turns = list(csv.DictReader((RAW / "part3_turns.csv").open(encoding="utf-8")))
        probes = list(csv.DictReader((RAW / "part3_probes.csv").open(encoding="utf-8")))
        per_turn = {s: sorted({int(r["turn"]) for r in turns if r["setting"] == s}) for s in SETTINGS}
        per_probe = {s: len([r for r in probes if r["setting"] == s]) for s in SETTINGS}
        ok = all(per_turn[s] == list(range(1, 31)) for s in SETTINGS) and all(per_probe[s] == 5 for s in SETTINGS)
        record("part3_raw_sweep_data_complete", ok, f"turns per setting={ {s: len(v) for s, v in per_turn.items()} }, probes per setting={per_probe}")
        conf = json.loads((RAW / "part3_run_config.json").read_text(encoding="utf-8"))
        info["sweep_source_fingerprint"] = conf.get("source_fingerprint")
        info["sweep_model"] = conf.get("chat_model")
    except Exception as exc:  # noqa: BLE001
        record("part3_raw_sweep_data_complete", False, f"{type(exc).__name__}: {exc}")
    try:
        text = (REPORT_DIR / "METRICS.md").read_text(encoding="utf-8")
        needed = ["SHORT_TERM_N=4", "SHORT_TERM_N=12", "SHORT_TERM_N=30", "10,000"]
        record("part3_metrics_tables_present", all(n in text for n in needed), f"METRICS.md contains {[n for n in needed if n in text]}")
    except Exception as exc:  # noqa: BLE001
        record("part3_metrics_tables_present", False, f"{type(exc).__name__}: {exc}")
    try:
        scores = json.loads((RAW / "part3_probe_scores.json").read_text(encoding="utf-8"))
        record("part3_probe_scores_saved_for_all_settings", set(scores) >= set(SETTINGS) and all(len(v["probes"]) == 5 for v in scores.values()),
               f"mean scores={ {k: v['mean_score'] for k, v in scores.items()} }")
    except Exception as exc:  # noqa: BLE001
        record("part3_probe_scores_saved_for_all_settings", False, f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- Part 4
def check_part4() -> None:
    from src import file_memory as fm

    agent = (REPO_ROOT / "AGENT.md").read_text(encoding="utf-8")
    headings = [h[3:].strip().lower() for h in agent.splitlines() if h.startswith("## ")]
    categories = [c for c in ["project description", "technology stack", "coding conventions", "testing approach", "prohibited actions"] if c in headings]
    instructions = [l for l in agent.splitlines() if l.lstrip().startswith(("- ", "1. ", "2. ", "3. ", "4. ", "5. "))]
    section = agent.split("## Code review output rules")[0]
    count = sum(1 for l in section.splitlines() if l.lstrip().startswith(("- ", "1. ", "2. ", "3. ", "4. ", "5. ")))
    record("part4_agent_md_has_5_instructions_in_3_categories", count >= 5 and len(categories) >= 3,
           f"{count} instruction lines (excluding code-review rules), categories={categories}")

    original = (REPORT_DIR / "MEMORY_original.md").read_text(encoding="utf-8")
    truth = yaml.safe_load((REPORT_DIR / "consolidation_truth.yaml").read_text(encoding="utf-8"))
    facts, _ = fm.split_memory(original)
    lowered = [f.lower() for f in facts]
    dup_ok = all(sum(1 for f in lowered if g["key"].lower() in f) == g["original_count"] for g in truth["duplicate_groups"])
    con_ok = all(any(c["keeper"].lower() in f for f in lowered) and any(c["loser"].lower() in f for f in lowered) for c in truth["contradictions"])
    record("part4_original_memory_has_55_lines_3plus_duplicates_3plus_contradictions",
           len(original.splitlines()) == 55 and dup_ok and con_ok and len(truth["duplicate_groups"]) >= 3 and len(truth["contradictions"]) >= 3,
           f"{len(original.splitlines())} lines, {len(truth['duplicate_groups'])} duplicate groups, {len(truth['contradictions'])} contradictions")

    consolidated = (REPORT_DIR / "MEMORY_consolidated.md").read_text(encoding="utf-8")
    run = load_script("run_consolidation_hw06")
    saved = json.loads((RAW / "consolidation_result.json").read_text(encoding="utf-8"))
    report = fm.ConsolidationReport(**{k: v for k, v in saved["report"].items()})
    results, wrong = run.evaluate(consolidated, truth, report)
    failed = [n for n, ok, _ in results if not ok]
    critical_kept = any("[critical]" in l and "peanut allergy" in l for l in fm.split_memory(consolidated)[0])
    fact_lines_c, conflict_lines_c = fm.split_memory(consolidated)
    no_loss = next(ok for n, ok, _ in results if n.startswith("no silent deletion"))
    # Hard requirements: under 40 lines, nothing silently deleted, the [critical] allergy still in Facts, conflicts section present.
    record("part4_consolidated_memory_under_40_lines_nothing_silently_deleted",
           len(consolidated.splitlines()) < 40 and no_loss and critical_kept and fm.CONFLICTS_HEADING in consolidated,
           f"{len(consolidated.splitlines())} lines; accounting ok: {no_loss}; [critical] allergy kept in Facts: {critical_kept}")
    # Quality of the model's contradiction/duplicate decisions is reported, not asserted: it depends on qwen3:8b.
    info["consolidation_quality"] = {
        "checks_passed": f"{len(results) - len(failed)}/{len(results)}",
        "failed_checks": failed,
        "contradictions_resolved_incorrectly": wrong,
        "model": saved.get("model"),
    }

    now = datetime.now(timezone.utc)
    stamped = fm.stamp_consolidated(consolidated, now)
    fresh_small = fm.stamp_consolidated("# MEMORY.md\n- [2026-10-16] one fact\n", now)
    stale_small = fm.stamp_consolidated("# MEMORY.md\n- [2026-10-16] one fact\n", datetime(2026, 1, 1, tzinfo=timezone.utc))
    long_fresh = fm.stamp_consolidated("# MEMORY.md\n" + "".join(f"- fact {i}\n" for i in range(45)), now)
    trigger_ok = (fm.needs_consolidation(original, now) and not fm.needs_consolidation(stamped, now) and not fm.needs_consolidation(fresh_small, now)
                  and fm.needs_consolidation(stale_small, now) and fm.needs_consolidation(long_fresh, now))
    record("part4_consolidation_trigger_40_lines_or_24_hours", trigger_ok,
           "original(55 lines, stale)=due, consolidated=not due, 1 fact fresh=not due, 1 fact 9 months old=due, 46 lines fresh=due")

    class Stub:
        """Offline stand-in for the model so the commands can be tested without Ollama."""

        def complete(self, messages, tools=None, *, temperature=0.0, response_format=None):
            from types import SimpleNamespace
            system = messages[0]["content"]
            if system.startswith("You consolidate"):
                return SimpleNamespace(content=json.dumps({"decisions": []}))
            if response_format is not None:
                return SimpleNamespace(content=json.dumps({"facts": [{"fact": "User wants verification checks to run offline.", "critical": False}]}))
            return SimpleNamespace(content="ok")
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        shutil.copyfile(REPORT_DIR / "MEMORY_consolidated.md", Path(tmp) / "MEMORY.md")
        session = fm.FileMemorySession(Stub(), REPO_ROOT / "AGENT.md", Path(tmp) / "MEMORY.md")
        help_text, memory_text, compact_text = session.handle("/help"), session.handle("/memory"), session.handle("/compact")
        session.history = [{"role": "user", "content": "hi"}]
        dream_text = session.handle("/dream")
        prompt = session.system_prompt()
    ok = (all(c in help_text for c in ["/memory", "/compact", "/dream", "/help"]) and "MEMORY.md" in memory_text
          and "Before:" in compact_text and "After:" in compact_text and "dream" in dream_text.lower()
          and "AGENT.md" in prompt and "MEMORY.md" in prompt)
    record("part4_commands_help_memory_compact_dream_work", ok, "commands run offline with a stub model; /compact printed Before/After counts; system prompt contains both files")

    gen = RAW / "agent_md_compliance.json"
    compliance = load_script("check_agent_md_compliance_hw06")
    ref = compliance.check_files([REPO_ROOT / "src/notice_text.py", REPO_ROOT / "tests/test_notice_text_hw06.py"])
    with tempfile.TemporaryDirectory() as tmp:  # negative control: code that breaks the conventions must be reported as failing
        bad = Path(tmp) / "bad_sample.py"
        bad.write_text('def normalize_notice_title(title, max_length=100):\n    """\n    Multi-line docstring\n    """\n    print(title)\n    return " ".join(title.split())\n', encoding="utf-8")
        control = compliance.check_files([bad])
    control_failed = {r["rule"] for r in control if not r["passed"]}
    try:
        g = json.loads(gen.read_text(encoding="utf-8"))
        info["generated_function"] = {"model": g.get("model"), "attempts": len(g["attempts"]), "final_passed": bool(g.get("final_passed")),
                                      "failed_rules_last_attempt": [r["rule"] for r in g["attempts"][-1]["results"] if not r["passed"]]}
        evidence = True
    except Exception:  # noqa: BLE001
        evidence = False
    record("part4_function_follows_agent_md_checked", all(r["passed"] for r in ref) and {"R1", "R2", "R5"} <= control_failed and evidence,
           f"reference function {sum(r['passed'] for r in ref)}/{len(ref)} rules; non-compliant control fails {sorted(control_failed)}; "
           f"generated-function evidence recorded: {evidence} (its pass/fail is in info.generated_function)")


# ---------------------------------------------------------------- tests, models, immutability
def check_offline_tests() -> None:
    suites = [("test_doc_api_hw06.py", "36/36"), ("test_memory_api_hw06.py", "/"), ("test_file_memory_hw06.py", "/")]
    results = []
    for script, marker in suites:
        try:
            p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=240)
            last = (p.stdout.strip().splitlines() or ["no output"])[-1]
            ok = p.returncode == 0 and "checks passed" in last
            if marker != "/":
                ok = ok and marker in last
            results.append((script, ok, last))
        except Exception as exc:  # noqa: BLE001
            results.append((script, False, f"{type(exc).__name__}: {exc}"))
    record("offline_test_suites_pass", all(ok for _, ok, _ in results), "; ".join(f"{s}: {last}" for s, _, last in results))


def check_ollama() -> None:
    try:
        names = {m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=10).json().get("models", [])}
        have = {n for n in names if n.startswith("qwen3:8b") or n.startswith("nomic-embed-text")}
        record("ollama_has_chat_and_embedding_models", any(n.startswith("qwen3:8b") for n in have) and any(n.startswith("nomic-embed-text") for n in have),
               f"found {sorted(have)}")
    except requests.RequestException as exc:
        record("ollama_has_chat_and_embedding_models", False, f"{type(exc).__name__} on {OLLAMA_URL}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPORT_DIR / "verification.json"))
    args = ap.parse_args()
    rng = random.Random(VERIFY_SEED)
    code_before = tree_hash("code", "src")

    check_backend()
    check_part1(rng)
    user = check_part2(rng)
    check_mongo_collections(user)
    check_part3()
    check_part4()
    check_offline_tests()
    check_ollama()
    code_after = tree_hash("code", "src")
    record("verification_did_not_modify_application_code", code_before == code_after, f"sha256 of code/ and src/ before == after: {code_before[:12]}")

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "homework_number": HOMEWORK_NUMBER,
        "sid4": SID4,
        "commit_hash": get_commit_hash(),
        "model_configuration": MODEL_CONFIG,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "info": info,
        "checks_passed": passed,
        "checks_total": len(checks),
        "all_passed": passed == len(checks),
        "checks": checks,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} checks passed.\nWrote {out}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
