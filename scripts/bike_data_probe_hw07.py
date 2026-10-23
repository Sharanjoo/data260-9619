"""HW7 Part 4 look-before-building probe (read-only except a download cache under data/baywheels_raw/, which is
git-ignored).

   python scripts\\bike_data_probe_hw07.py --text            # print the visible text of the pricing page and the 2026 price-change page
   python scripts\\bike_data_probe_hw07.py --trips 202410    # download one month of Bay Wheels trips and describe it
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_baywheels_hw07 import TextOnly, fetch  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "data" / "baywheels_raw"
PAGES = ["https://lyftbikes.com/pricing", "https://lyftbikes.com/blog/price-change-2026"]
S3 = "https://s3.amazonaws.com/baywheels-data/"
UA = {"User-Agent": "Mozilla/5.0 (HW7 DATA-260 student; Sharan Lourduraj)"}


def show_text() -> None:
    for url in PAGES:
        final, status, _ctype, body = fetch(url)
        parser = TextOnly()
        parser.feed(body.decode("utf-8", errors="replace"))
        text = " ".join(parser.parts)
        print(f"\n===== {url}  (status {status}, {len(text)} chars) =====")
        print(text)


def pct(sorted_vals, q):
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def describe_trips(month: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    name = f"{month}-baywheels-tripdata.csv.zip"
    zpath = CACHE / name
    if not zpath.exists():
        print(f"downloading {S3}{name} ...")
        req = urllib.request.Request(S3 + name, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as resp:
            zpath.write_bytes(resp.read())
    print(f"{zpath} ({zpath.stat().st_size / 1e6:.1f} MB)")
    with zipfile.ZipFile(zpath) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv") and not m.startswith("__MACOSX")]
        print("csv members:", members)
        with zf.open(members[0]) as fh:
            reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))
            print("columns:", reader.fieldnames)
            rows, types, who, durs, days, bad = 0, Counter(), Counter(), [], Counter(), 0
            first = None
            for row in reader:
                rows += 1
                first = first or row
                types[row.get("rideable_type")] += 1
                who[row.get("member_casual")] += 1
                try:
                    a = datetime.fromisoformat(row["started_at"][:19])
                    b = datetime.fromisoformat(row["ended_at"][:19])
                    d = (b - a).total_seconds() / 60.0
                    if d < 0:
                        bad += 1
                        continue
                    durs.append(d)
                    days[a.date().isoformat()] += 1
                except (KeyError, ValueError):
                    bad += 1
    durs.sort()
    print(f"rows: {rows}  unparseable/negative durations: {bad}")
    print("first row:", first)
    print("rideable_type:", dict(types))
    print("member_casual:", dict(who))
    if durs:
        print("duration minutes: " + ", ".join(f"p{int(q * 100)}={pct(durs, q):.1f}" for q in (0.05, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)) + f", max={durs[-1]:.0f}")
        print(f"share over 30 min: {sum(1 for d in durs if d > 30) / len(durs):.1%}; over 45 min: {sum(1 for d in durs if d > 45) / len(durs):.1%}")
    print(f"days covered: {len(days)} ({min(days)} to {max(days)})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--trips", metavar="YYYYMM")
    args = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    print("Student: Sharan Lourduraj (SJSU 018169619)  HW7 Part 4 data probe")
    if args.text:
        show_text()
    if args.trips:
        describe_trips(args.trips)
    if not (args.text or args.trips):
        ap.error("choose --text and/or --trips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
