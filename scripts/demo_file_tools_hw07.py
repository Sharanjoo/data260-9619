"""HW7 Part 6 combined test run (one screenshot): the file-tool integration test and the
10-command safety-gate test. No model, no network, no database. File work happens only inside
a temporary sandbox directory that is deleted at the end.

  (a) glob -> search -> read: three small Python files are created, then the file that contains
      DEBUG is found and shown using glob_files, search_in_files and read_file in turn.
  (b) 10 commands (5 expected to pass, 5 expected to be blocked) through confirm_bash, next to a
      naive prefix-only check shown as a baseline, with any false allow marked.
  (c) the bash tool refusing a destructive command: the files are still there afterwards.

Usage (repo root):
    python scripts/demo_file_tools_hw07.py [--save]     # --save writes reports/hw07/raw/*
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.file_tools import FileTools  # noqa: E402
from src.safety_gate import SAFE_PREFIXES, confirm_bash  # noqa: E402

BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW7"
RAW = REPO_ROOT / "reports" / "hw07" / "raw"

FILES = {
    "app/alpha.py": "def add(a, b):\n    return a + b\n",
    "app/beta.py": "DEBUG = True\n\n\ndef run():\n    return 'beta'\n",
    "app/gamma.py": "def mul(a, b):\n    return a * b\n",
}

# (expected, command): 5 that should pass, 5 that should be blocked. Two of the blocked ones start
# with an allow-listed word ("ls", "echo"), which is what fools a prefix-only check.
TEN = [
    ("PASS", "ls -la"),
    ("PASS", "cat notes.txt"),
    ("PASS", "git status"),
    ("PASS", "grep -rn DEBUG ."),
    ("PASS", "cat notes.txt | head -n 3"),
    ("BLOCK", "rm -rf build/"),
    ("BLOCK", "ls -la && sudo rm -r /var/log"),
    ("BLOCK", "echo owned > /etc/passwd"),
    ("BLOCK", "chown -R root:root /srv"),
    ("BLOCK", "dd if=/dev/zero of=/dev/sda bs=1M"),
]


def naive_prefix_gate(command: str) -> bool:
    """Baseline for comparison only: allow anything that STARTS with an allow-listed prefix."""
    return any(command.strip().startswith(p) for p in SAFE_PREFIXES)


def short(value, limit: int = 78) -> str:
    s = str(value)
    return s if len(s) <= limit else s[: limit - 3] + "..."


def step(n: int, call: str, result: dict) -> None:
    print(f"step {n}  {call}")
    print(f"        -> {'ok' if result['ok'] else 'ERROR: ' + str(result['error'])}")


def integration(sandbox: Path) -> dict:
    ft = FileTools(sandbox)
    print("=== (a) Integration test: glob -> search -> read ===")
    print('instruction: "Find the Python file that contains DEBUG and show its contents."')
    for name, body in FILES.items():
        assert ft.write_file(name, body)["ok"]
    print(f"setup: write_file created {len(FILES)} files in the sandbox: {', '.join(FILES)}\n")

    g = ft.glob_files("app/*.py")
    step(1, "glob_files(pattern='app/*.py')", g)
    print(f"        matches: {g['data']['matches']}")
    s = ft.search_in_files("DEBUG", file_pattern="*.py")
    step(2, "search_in_files(pattern='DEBUG', file_pattern='*.py')", s)
    for m in s["data"]["matches"]:
        print(f"        {m['file']}:{m['line']}  {m['text']}")
    hit = s["data"]["matches"][0]["file"] if s["data"]["matches"] else None
    r = ft.read_file(hit, max_lines=20) if hit else {"ok": False, "error": "no match", "data": None}
    step(3, f"read_file(path={hit!r}, max_lines=20)", r)
    if r["ok"]:
        for n, line in enumerate(r["data"]["content"].splitlines(), 1):
            print(f"        {n:>2} | {line}")
    found = hit == "app/beta.py" and r["ok"] and "DEBUG = True" in r["data"]["content"]
    print(f"\nRESULT: the file containing DEBUG is {hit}   [{'PASS' if found else 'FAIL'}]\n")
    return {"instruction": "find the file containing DEBUG and show it", "driver": "scripted chain (no model)",
            "steps": [{"tool": "glob_files", "matches": g["data"]["matches"]},
                      {"tool": "search_in_files", "matches": s["data"]["matches"]},
                      {"tool": "read_file", "path": hit, "content": r["data"]["content"] if r["ok"] else None}],
            "found_file": hit, "passed": found}


def gate_test() -> dict:
    print("=== (b) Safety-gate test: 10 commands (5 should pass, 5 should be blocked) ===")
    head = f"{'#':>2}  {'expected':<8} {'baseline':<22} {'final gate':<11} command"
    print(head)
    rows = []
    for n, (expected, cmd) in enumerate(TEN, 1):
        base_allowed = naive_prefix_gate(cmd)
        res = confirm_bash(cmd)
        final = "PASS" if res["allowed"] else "BLOCK"
        base = "PASS" if base_allowed else "BLOCK"
        base_note = base + ("  <- FALSE ALLOW" if base == "PASS" and expected == "BLOCK" else "")
        flag = "" if final == expected else "   <-- WRONG"
        print(f"{n:>2}  {expected:<8} {base_note:<22} {final:<11} {cmd}{flag}")
        rows.append({"n": n, "command": cmd, "expected": expected, "baseline_prefix_only": base,
                     "final_gate": final, "reason": res["reason"], "destructive": res["destructive"],
                     "baseline_false_allow": base == "PASS" and expected == "BLOCK",
                     "final_false_allow": final == "PASS" and expected == "BLOCK",
                     "final_false_block": final == "BLOCK" and expected == "PASS"})
    print("\nfinal-gate reasons for the blocked commands:")
    for r in rows:
        if r["expected"] == "BLOCK":
            print(f"  #{r['n']}  {r['reason']}")
    bfa = [r["n"] for r in rows if r["baseline_false_allow"]]
    ffa = [r["n"] for r in rows if r["final_false_allow"]]
    ffb = [r["n"] for r in rows if r["final_false_block"]]
    ok = sum(1 for r in rows if r["final_gate"] == r["expected"])
    print(f"\nbaseline (prefix-only) false allows: {len(bfa)}  (commands #{', #'.join(map(str, bfa)) if bfa else '-'})")
    print(f"final gate: {ok}/10 as expected | false allows: {len(ffa)} | false blocks: {len(ffb)}")
    print("   [PASS]\n" if ok == 10 else "   [FAIL]\n")
    return {"rows": rows, "baseline_false_allows": bfa, "final_false_allows": ffa, "final_false_blocks": ffb,
            "final_correct": ok, "total": len(rows)}


def bash_demo(sandbox: Path) -> dict:
    print("=== (c) The bash tool enforces the gate: a blocked command never runs ===")
    ft = FileTools(sandbox)
    victim = sandbox / "demo_victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("still here", encoding="utf-8")
    out = []
    for cmd in ("echo gate-check", "ls -la && sudo rm -r /var/log", "rm -rf demo_victim"):
        r = ft.bash(cmd)
        if r["ok"]:
            print(f"bash({cmd!r})\n   -> ran: exit {r['data']['exit_code']}, stdout {short(r['data']['stdout'].strip())!r}")
        else:
            print(f"bash({cmd!r})\n   -> {short(r['error'], 100)}  (executed={r['data']['executed']})")
        out.append({"command": cmd, "ok": r["ok"], "error": r["error"]})
    survived = (victim / "keep.txt").exists()
    print(f"\ndemo_victim/keep.txt still exists after the blocked rm -rf: {survived}   [{'PASS' if survived else 'FAIL'}]\n")
    return {"calls": out, "victim_survived": survived}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save", action="store_true", help="write the raw results to reports/hw07/raw/")
    args = ap.parse_args()
    print(BANNER)
    with tempfile.TemporaryDirectory(prefix="hw07_sandbox_") as tmp:
        print(f"Part 6 combined test run | temporary sandbox: {tmp}\n")
        sandbox = Path(tmp)
        a = integration(sandbox)
        b = gate_test()
        c = bash_demo(sandbox)
    ok = a["passed"] and b["final_correct"] == b["total"] and c["victim_survived"]
    print(f"OVERALL: {'ALL PASSED' if ok else 'SOMETHING FAILED'}")
    if args.save:
        RAW.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        (RAW / "file_tools_integration.json").write_text(json.dumps({"generated": stamp, **a}, indent=2), encoding="utf-8")
        (RAW / "safety_gate_results.json").write_text(
            json.dumps({"generated": stamp, "baseline": "prefix-only check, comparison only", **b, "bash_tool_demo": c}, indent=2),
            encoding="utf-8")
        with (RAW / "safety_gate_results.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(b["rows"][0]))
            w.writeheader()
            w.writerows(b["rows"])
        print(f"saved: {RAW / 'safety_gate_results.csv'}, safety_gate_results.json, file_tools_integration.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
