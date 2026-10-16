"""HW6 Part 3: run the same 30-turn conversation at SHORT_TERM_N = 4, 12, 30 and with the
compression policy, ask the five memory probes after each run, and save the raw data.

    python scripts/recorded_run_hw06.py -- python scripts/run_memory_sweep_hw06.py

It is RESUMABLE (a full sweep takes hours on a laptop CPU): progress is kept in
reports/hw06/raw/sweep_state.json, so if the run is interrupted just start it again and it
continues at the next turn. Useful options:

    --only N12            run one setting (N4, N12, N30, POLICY)
    --limit-turns 3       tiny dry run (writes to a different raw folder name with --out)
    --fresh               ignore saved progress and start every selected setting over

Outputs (reports/hw06/raw/): part3_turns.csv (one row per chat turn), part3_probes.csv
(one row per probe), part3_probe_scores.json (memory_probes.yaml scoring results).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports/hw06"
BASE = os.environ.get("HW6_BASE_URL", "http://localhost:8619").rstrip("/")

# label -> (SHORT_TERM_N, compression policy)
SETTINGS = {
    "N4": (4, "none"),
    "N12": (12, "none"),
    "N30": (30, "none"),
    "POLICY": (30, "compress_old_assistant"),
}
TURN_FIELDS = [
    "setting", "short_term_n", "policy", "turn", "user_id", "session_id",
    "prompt_tokens", "completion_tokens",
    "tok_system_primer", "tok_long_term_summary", "tok_short_term_window", "tok_episodic_facts", "tok_current_message",
    "reply_latency_ms", "latency_ms", "model_duration_ms",
    "overhead_prompt_tokens", "overhead_completion_tokens",
    "window_count", "episodes_retrieved", "session_summary_used", "lifetime_summary_used",
    "session_summary_updated", "lifetime_summary_updated", "episodes_stored", "timestamp",
]
PROBE_FIELDS = [
    "setting", "short_term_n", "policy", "probe_id", "question", "reply", "score",
    "groups_matched", "groups_required", "stale_mentioned", "said_unknown",
    "prompt_tokens", "completion_tokens", "latency_ms", "retrieved_facts", "timestamp",
]


def local_fingerprint() -> str:
    """Same recipe as code/memory_api/fingerprint.py, computed from the files in the repo."""
    package_dir = ROOT / "code/memory_api"
    digest = hashlib.sha256()
    for path in sorted(list(package_dir.glob("*.py")) + list(package_dir.glob("*.html"))):
        digest.update(path.name.encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()[:16]


def check_server(out_dir: Path) -> bool:
    """Ask the running container which settings/code it has and make sure it matches the repo."""
    try:
        r = requests.get(f"{BASE}/api/memory-config", timeout=30)
        r.raise_for_status()
        cfg = r.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"Cannot read {BASE}/api/memory-config ({exc}).\nThe container is missing or running an OLD image: "
              "run 'docker compose up --build -d' and try again.")
        return False
    mine = local_fingerprint()
    cfg["repo_fingerprint"] = mine
    cfg["checked_at"] = utc_now()
    (out_dir / "part3_run_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("Server settings:", {k: v for k, v in cfg.items() if k not in ("checked_at",)})
    if cfg["source_fingerprint"] != mine:
        print(f"\nSTOP: the container runs code {cfg['source_fingerprint']} but your repo has {mine}.\n"
              "Run 'docker compose up --build -d' so the sweep uses the current code.")
        return False
    return True


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def score_reply(reply: str, probe: dict, unknown_phrases: list[str]) -> dict:
    """Rule-based 1-5 score following the rubric in memory_probes.yaml."""
    text = reply.lower().replace("’", "'")
    groups = probe["required_groups"]
    matched = sum(1 for group in groups if any(phrase in text for phrase in group))
    stale = any(phrase in text for phrase in probe.get("stale", []))
    unknown = any(phrase in text for phrase in unknown_phrases)
    fraction = matched / len(groups)
    if fraction == 1 and not stale:
        score = 5
    elif fraction == 1:
        score = 4
    elif fraction >= 0.5:
        score = 3
    elif unknown or stale:
        score = 1
    else:
        score = 2
    return {"score": score, "groups_matched": matched, "groups_required": len(groups),
            "stale_mentioned": stale, "said_unknown": unknown}


def post_chat(body: dict, retries: int = 3) -> dict:
    last = ""
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(f"{BASE}/api/chat", json=body, timeout=3600)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as exc:
            last = str(exc)
        print(f"    attempt {attempt} failed: {last}")
        time.sleep(10)
    raise RuntimeError(last)


def append_rows(path: Path, fields: list[str], rows: list[dict]) -> None:
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if new:
            writer.writeheader()
        writer.writerows(rows)


def turn_row(label, n, policy, turn, data) -> dict:
    m, used, ev = data["metrics"], data["memory_used"], data["memory_events"]
    comp = m["tokens_by_component"]
    return {
        "setting": label, "short_term_n": n, "policy": policy, "turn": turn,
        "user_id": data["user_id"], "session_id": data["session_id"],
        "prompt_tokens": m["prompt_tokens"], "completion_tokens": m["completion_tokens"],
        "tok_system_primer": comp["system_primer"], "tok_long_term_summary": comp["long_term_summary"],
        "tok_short_term_window": comp["short_term_window"], "tok_episodic_facts": comp["episodic_facts"],
        "tok_current_message": comp["current_message"],
        "reply_latency_ms": m["reply_latency_ms"], "latency_ms": m["latency_ms"], "model_duration_ms": m["model_duration_ms"],
        "overhead_prompt_tokens": m["memory_overhead_prompt_tokens"],
        "overhead_completion_tokens": m["memory_overhead_completion_tokens"],
        "window_count": used["short_term"]["count"], "episodes_retrieved": len(used["episodic"]),
        "session_summary_used": bool(used["long_term"]["session_summary"]),
        "lifetime_summary_used": bool(used["long_term"]["lifetime_summary"]),
        "session_summary_updated": ev["session_summary_updated"], "lifetime_summary_updated": ev["lifetime_summary_updated"],
        "episodes_stored": len(ev["episodes_stored"]), "timestamp": utc_now(),
    }


def run_setting(label, state, conversation, probes_cfg, out_dir, limit_turns) -> None:
    n, policy = SETTINGS[label]
    st = state[label]
    turns = sorted(conversation["turns"].items())[: limit_turns or None]
    print(f"\n=== {label}: SHORT_TERM_N={n}, policy={policy}, user_id={st['user_id']} ===")
    while st["next_turn"] <= len(turns):
        number, message = turns[st["next_turn"] - 1]
        body = {"user_id": st["user_id"], "message": message, "short_term_n": n, "compression_policy": policy}
        if st.get("session_id"):
            body["session_id"] = st["session_id"]
        data = post_chat(body)
        st["session_id"] = data["session_id"]
        row = turn_row(label, n, policy, number, data)
        append_rows(out_dir / "part3_turns.csv", TURN_FIELDS, [row])
        st["next_turn"] += 1
        save_state(out_dir, state)
        print(f"  turn {number:02d}/{len(turns)}  prompt={row['prompt_tokens']:>5}  completion={row['completion_tokens']:>3}  "
              f"reply={row['reply_latency_ms']/1000:6.1f}s  total={row['latency_ms']/1000:6.1f}s  "
              f"window={row['window_count']} facts={row['episodes_retrieved']}")

    probes = probes_cfg["probes"]
    done = set(st.get("probes_done", []))
    for probe in probes:
        if probe["id"] in done:
            continue
        body = {"user_id": st["user_id"], "session_id": st["session_id"], "message": probe["question"],
                "short_term_n": n, "compression_policy": policy, "read_only": True}
        data = post_chat(body)
        result = score_reply(data["reply"], probe, probes_cfg["unknown_phrases"])
        row = {
            "setting": label, "short_term_n": n, "policy": policy, "probe_id": probe["id"],
            "question": probe["question"], "reply": " ".join(data["reply"].split()), **result,
            "prompt_tokens": data["metrics"]["prompt_tokens"], "completion_tokens": data["metrics"]["completion_tokens"],
            "latency_ms": data["metrics"]["latency_ms"],
            "retrieved_facts": " | ".join(e["fact"] for e in data["memory_used"]["episodic"]),
            "timestamp": utc_now(),
        }
        append_rows(out_dir / "part3_probes.csv", PROBE_FIELDS, [row])
        st.setdefault("probes_done", []).append(probe["id"])
        save_state(out_dir, state)
        print(f"  probe {probe['id']}: score {result['score']}  ({probe['question']})\n      -> {row['reply'][:160]}")
    write_scores(out_dir)


def write_scores(out_dir: Path) -> None:
    path = out_dir / "part3_probes.csv"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    scores: dict = {}
    for row in rows:
        scores.setdefault(row["setting"], {"probes": {}, "mean_score": None})["probes"][row["probe_id"]] = {
            "score": int(row["score"]), "reply": row["reply"], "retrieved_facts": row["retrieved_facts"],
        }
    for entry in scores.values():
        values = [p["score"] for p in entry["probes"].values()]
        entry["mean_score"] = round(sum(values) / len(values), 2)
    (out_dir / "part3_probe_scores.json").write_text(json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8")


def load_state(out_dir: Path) -> dict:
    path = out_dir / "sweep_state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(out_dir: Path, state: dict) -> None:
    (out_dir / "sweep_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=list(SETTINGS), nargs="+", help="run only these settings")
    parser.add_argument("--limit-turns", type=int, default=0, help="dry run: only the first K turns")
    parser.add_argument("--fresh", action="store_true", help="ignore saved progress for the selected settings")
    parser.add_argument("--out", default="reports/hw06/raw", help="output folder (relative to the repo root)")
    args = parser.parse_args()

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    conversation = yaml.safe_load((REPORT_DIR / "conversation_30.yaml").read_text(encoding="utf-8"))
    probes_cfg = yaml.safe_load((REPORT_DIR / "memory_probes.yaml").read_text(encoding="utf-8"))
    state = load_state(out_dir)
    labels = args.only or list(SETTINGS)
    run_id = int(time.time())
    for label in labels:
        if args.fresh or label not in state:
            # a brand-new user per setting so episodes/summaries from one setting never leak into another
            state[label] = {"user_id": f"sweep-{label.lower()}-{run_id}", "session_id": None, "next_turn": 1, "probes_done": []}
            if args.fresh:
                print(f"{label}: starting over with a fresh user (old rows stay in the CSV; delete them if you want a clean file)")
    save_state(out_dir, state)

    print(f"HW6 Part 3 sweep against {BASE}; settings: {', '.join(labels)}")
    if not check_server(out_dir):
        return 3
    started = time.time()
    for label in labels:
        try:
            run_setting(label, state, conversation, probes_cfg, out_dir, args.limit_turns)
        except RuntimeError as exc:
            print(f"\nSTOPPED in {label}: {exc}\nRe-run the same command to resume from the next turn.")
            return 1
        except requests.ConnectionError:
            print(f"\nCannot reach {BASE}. Start the stack and run the same command again to resume.")
            return 2
    print(f"\nSweep finished in {(time.time() - started) / 60:.1f} minutes. Raw data: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
