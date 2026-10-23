"""HW7 Part 4 command-line runner for the Bay Wheels agent (the Streamlit UI runs the same code).

   python scripts\\run_bike_agent_hw07.py --scenario M [--save]      # membership scenario
   python scripts\\run_bike_agent_hw07.py --scenario P [--save]      # pay-per-use scenario
   python scripts\\run_bike_agent_hw07.py --csv my.csv --url https://...

Prints the live timeline, the final answer, and a check of the agent's numbers against the independent reference
calculation in src/bike_pricing.py (the agent never sees that calculation).
Needs Ollama with qwen3:8b and:  pip install langchain langgraph langchain-ollama
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.bike_agent import stream_agent  # noqa: E402
from src.bike_pricing import evaluate_trips, snapshot_supports_prices  # noqa: E402
from src.bike_tools import BikeTools  # noqa: E402

BANNER = "Student: Sharan Lourduraj (SJSU 018169619)  SID4 9619  HW7 Part 4 (Bay Wheels agent)"
PRICING_URL = "https://www.lyft.com/bikes/bay-wheels/pricing"
SCENARIOS = {"M": REPO / "data/bike/scenario_M_membership.csv", "P": REPO / "data/bike/scenario_P_payperuse.csv"}
RAW = REPO / "reports/hw07/raw"
TOLERANCE = 0.02  # agent totals must be within 2% of the reference


def close(a, b) -> bool:
    return a is not None and b is not None and abs(a - b) <= max(0.5, TOLERANCE * abs(b))


def check_against_reference(result: dict, ref: dict, snapshot_text: str | None) -> dict:
    p = result["parsed"]
    checks = {
        "decision matches reference": p["decision"] == ref["decision"],
        "pay-per-use total within 2%": close(p["pay_per_use_total"], ref["pay_per_use_total"]),
        "membership total within 2%": close(p["membership_total"], ref["membership_total"]),
        "finished with a final answer": result["reason"] == "final_answer",
        "pricing page was fetched": bool(result["snapshots"]),
    }
    if snapshot_text is not None:
        checks["snapshot still supports the reference prices"] = not snapshot_supports_prices(snapshot_text)
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=list(SCENARIOS))
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--url", default=PRICING_URL)
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--label", default=None)
    ap.add_argument("--max-steps", type=int, default=14)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    csv_path = args.csv or (SCENARIOS[args.scenario] if args.scenario else None)
    if not csv_path:
        ap.error("choose --scenario or --csv")
    label = args.label or (f"scenario_{args.scenario}" if args.scenario else csv_path.stem)
    print(BANNER)
    print(f"csv={csv_path.name}  pricing url={args.url}  model={args.model}\n")
    tools = BikeTools(csv_path, [args.url], snapshot_dir=RAW / "bike_snapshots", label=label)
    print(f"uploaded trips: {tools.row_count} rows; table {tools.describe_table()}\n")

    result = None
    events = []
    for ev in stream_agent(tools, url=args.url, model=args.model, max_steps=args.max_steps):
        if ev["type"] == "tool_call":
            print(f"[step {ev['step']:>2}] CALL {ev['tool']} {json.dumps(ev['args'], ensure_ascii=False)[:300]}")
        elif ev["type"] == "observation":
            print(f"         -> {'ok' if ev['success'] else 'ERROR ' + str(ev['error'])}: {ev['summary'][:200]}")
        elif ev["type"] == "final":
            print("\nFINAL ANSWER\n" + (ev["text"] or ""))
        elif ev["type"] == "stop":
            result = ev
        events.append(ev)
    assert result is not None
    print(f"\nstop reason: {result['reason']}  steps: {result['steps']}  total time: {result['wall_s']} s  "
          f"tokens: {result['input_tokens']}+{result['output_tokens']}  error: {result['error']}")

    ref = evaluate_trips(csv_path)
    snap_text = None
    if result["snapshots"] and result["snapshots"][-1].get("file"):
        snap_text = (RAW / "bike_snapshots" / result["snapshots"][-1]["file"]).read_text(encoding="utf-8")
    checks = check_against_reference(result, ref, snap_text)
    print("\nREFERENCE (independent calculation, not shown to the agent)")
    print(f"  pay-per-use ${ref['pay_per_use_total']:.2f} | membership ${ref['membership_total']:.2f} "
          f"(pass ${ref['membership_pass_cost']:.2f} + per-minute ${ref['membership_residual']:.2f}) -> {ref['decision']}; "
          f"break-even {ref['break_even_rides_per_month']} rides/month vs actual {ref['rides_per_month']:.1f}")
    print(f"  agent said: {result['parsed']}")
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if result["snapshots"]:
        s = result["snapshots"][-1]
        print(f"\ncitation: {s['url']} accessed {s['accessed_at']} sha256 {s['sha256']} ({s['chars']} chars)")
    if args.save:
        RAW.mkdir(parents=True, exist_ok=True)
        out = RAW / f"bike_run_{label}.json"
        out.write_text(json.dumps({"label": label, "csv": str(csv_path.relative_to(REPO)).replace("\\", "/"), "url": args.url,
                                   "model": args.model, "result": {k: v for k, v in result.items() if k != "type"},
                                   "events": [e for e in events if e["type"] != "stop"], "reference": ref, "checks": checks},
                                  indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"saved {out.relative_to(REPO)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
