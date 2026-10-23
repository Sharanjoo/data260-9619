"""HW7 Part 4: the Bay Wheels pricing rules as plain data, and an independent reference calculation.

The prices come from the official Bay Wheels plans-and-pricing page (https://lyftbikes.com/pricing, reached from
https://www.lyft.com/bikes/bay-wheels/pricing) as captured on 2026-10-22. They are NOT used by the agent (the agent
must read them from the page with policy_retriever); they are used only to
  * check that a saved page snapshot still says what these numbers say (``snapshot_supports_prices``), and
  * compute the reference answer the agent's numbers are compared against (``evaluate_trips``).

Rules as read from the page (columns: Single ride | Day pass | Month pass | Lyft Bike annual | Lyft Pink):
  Single ride (pay per use): $1.00 to unlock + $0.19/min on a classic bike, $1.00 unlock + $0.49/min on an ebike.
  Month pass $29/month: classic bikes 45 min free then $0.17/min; ebikes free unlocks + $0.17/min.
Assumptions (the page does not state them): charges apply to the exact ride duration in minutes (no rounding up);
a month pass is bought for every calendar month in which the rider has at least one trip.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PRICES = {
    "unlock": 1.00,
    "ppu_classic_per_min": 0.19,
    "ppu_ebike_per_min": 0.49,
    "month_pass": 29.00,
    "member_classic_free_min": 45.0,
    "member_classic_overage_per_min": 0.17,
    "member_ebike_per_min": 0.17,
}

# strings that must all appear in a page snapshot for the numbers above to be trusted
SNAPSHOT_MARKERS = ["$29/month", "$1.00 to unlock", "$0.19/min", "45 min free, then $0.17/min", "$0.49/min",
                    "Free unlocks + $0.17/min"]

BASE_COLUMNS = ("rideable_type", "started_at", "ended_at")


def snapshot_supports_prices(text: str) -> List[str]:
    """Return the markers missing from the snapshot (empty list = the page still says what PRICES says)."""
    return [m for m in SNAPSHOT_MARKERS if m not in text]


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.strip()[:23].replace("Z", ""))


def trip_minutes(row: Dict[str, str]) -> float:
    return max(0.0, (_parse(row["ended_at"]) - _parse(row["started_at"])).total_seconds() / 60.0)


def ppu_cost(kind: str, minutes: float, p: Dict[str, float] = PRICES) -> float:
    rate = p["ppu_ebike_per_min"] if kind == "electric_bike" else p["ppu_classic_per_min"]
    return p["unlock"] + rate * minutes


def member_variable_cost(kind: str, minutes: float, p: Dict[str, float] = PRICES) -> float:
    """Per-trip charge on top of the month pass."""
    if kind == "electric_bike":
        return p["member_ebike_per_min"] * minutes
    return p["member_classic_overage_per_min"] * max(0.0, minutes - p["member_classic_free_min"])


def evaluate_trips(csv_path: Path, p: Dict[str, float] = PRICES) -> dict:
    """Reference pay-per-use vs month-pass cost for every trip in a CSV with rideable_type/started_at/ended_at."""
    with Path(csv_path).open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    n = len(rows)
    ppu = mvar = 0.0
    minutes_total = 0.0
    months = set()
    weeks: Dict[str, list] = defaultdict(lambda: [0, 0.0, 0.0])  # rides, minutes, ppu spend
    types: Dict[str, int] = defaultdict(int)
    for r in rows:
        m = trip_minutes(r)
        kind = r["rideable_type"]
        c = ppu_cost(kind, m, p)
        ppu += c
        mvar += member_variable_cost(kind, m, p)
        minutes_total += m
        start = _parse(r["started_at"])
        months.add(start.strftime("%Y-%m"))
        wk = weeks[start.strftime("%Y-%W")]
        wk[0] += 1
        wk[1] += m
        wk[2] += c
        types[kind] += 1
    n_months = len(months)
    membership = p["month_pass"] * n_months + mvar
    per_ride_saving = (ppu - mvar) / n if n else 0.0
    break_even = p["month_pass"] / per_ride_saving if per_ride_saving > 0 else None
    return {
        "rides": n, "months": n_months, "rides_per_month": n / n_months if n_months else 0.0,
        "avg_minutes": minutes_total / n if n else 0.0, "total_minutes": minutes_total, "bike_types": dict(types),
        "pay_per_use_total": round(ppu, 2), "membership_pass_cost": round(p["month_pass"] * n_months, 2),
        "membership_residual": round(mvar, 2), "membership_total": round(membership, 2),
        "break_even_rides_per_month": round(break_even, 1) if break_even else None,
        "decision": "Buy Monthly Membership" if membership < ppu else "Pay Per Ride/Minute",
        "difference": round(abs(ppu - membership), 2),
        "weekly": [{"week": k, "rides": v[0], "avg_minutes": round(v[1] / v[0], 2), "pay_per_use_spend": round(v[2], 2)}
                   for k, v in sorted(weeks.items())],
    }
