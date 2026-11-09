"""HW9: print a saved run from reports/hw09/RUN_LOG.txt (or any saved file) under the name banner, for report screenshots.

    python scripts/hw9_show_run.py part4_variants              latest recorded run whose command contains this text
    python scripts/hw9_show_run.py hw9_part2_run --tail 14     only the last 14 lines of that run
    python scripts/hw9_show_run.py --file data/hw09/lessons.json

Nothing is re-run and nothing is changed: it only reads the log the recorder wrote at the time of the run."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "reports" / "hw09" / "RUN_LOG.txt"
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW9"
START = re.compile(r"^\[(?P<ts>[^\]]+)\] Sharan Lourduraj \| START command: (?P<cmd>.*)$")


def blocks(text: str) -> list:
    out, cur = [], None
    for line in text.splitlines():
        m = START.match(line)
        if m:
            cur = {"ts": m["ts"], "cmd": m["cmd"], "lines": [line]}
            out.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("match", nargs="?", help="text that the command of the run contains")
    ap.add_argument("--file", help="print this file instead")
    ap.add_argument("--tail", type=int, default=0)
    ap.add_argument("--head", type=int, default=0)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{BANNER} | hw9_show_run")
    if args.file:
        path = ROOT / args.file
        print(f"file: {args.file}\n")
        print(path.read_text(encoding="utf-8"))
        return 0
    if not args.match:
        ap.error("give a text to match or --file")
    found = [b for b in blocks(LOG.read_text(encoding="utf-8")) if args.match in b["cmd"]]
    if not found:
        print(f"no recorded run matches '{args.match}' in {LOG.name}")
        return 1
    block = found[-1]
    lines = block["lines"]
    if args.head:
        lines = lines[:args.head]
    if args.tail:
        lines = lines[-args.tail:]
    print(f"from {LOG.name}: run started {block['ts']} ({len(found)} recorded run(s) match; showing the latest)\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
