"""Run and record the required 40-run non-determinism experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from code.agents_demo import load_input, run_pipeline  # noqa: E402
from src.model_client import ModelClientError, OllamaModelClient  # noqa: E402


TEMPERATURES = (0.7, 0.0)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def percentile(values: Iterable[float], percent: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percent / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(rows: list[dict[str, Any]], temperature: float) -> dict[str, Any]:
    selected = [row for row in rows if float(row["temperature"]) == temperature]
    if not selected:
        raise ValueError(f"no rows for temperature {temperature}")

    tag_sets = {tuple(sorted(tag.casefold() for tag in row["tags"])) for row in selected}
    occurrence_count: Counter[str] = Counter()
    for row in selected:
        occurrence_count.update({tag.casefold() for tag in row["tags"]})

    run_count = len(selected)
    all_runs = sorted(tag for tag, count in occurrence_count.items() if count == run_count)
    one_run = sorted(tag for tag, count in occurrence_count.items() if count == 1)
    latencies = [float(row["latency_ms"]) for row in selected]

    return {
        "runs": run_count,
        "distinct_tag_sets": len(tag_sets),
        "tags_in_all_runs": all_runs,
        "tags_in_exactly_one_run": one_run,
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 3),
            "p95": round(percentile(latencies, 95), 3),
            "p99": round(percentile(latencies, 99), 3),
        },
    }


def make_markdown(metrics: dict[str, Any], model: str, generated_at: str) -> str:
    temp07 = metrics["0.7"]
    temp00 = metrics["0.0"]

    def tags(values: list[str]) -> str:
        return ", ".join(f"`{value}`" for value in values) if values else "None"

    return f"""# Homework 1 Experiment Metrics

- Model: `{model}`
- Generated (UTC): `{generated_at}`
- Runs per temperature: {temp07['runs']}
- Percentile method: linear interpolation between adjacent ordered observations

## Tag variation

| Metric | Temp 0.7 | Temp 0.0 |
| --- | --- | --- |
| Distinct tag sets | {temp07['distinct_tag_sets']} | {temp00['distinct_tag_sets']} |
| Tags in all runs | {tags(temp07['tags_in_all_runs'])} | {tags(temp00['tags_in_all_runs'])} |
| Tags in exactly one run | {tags(temp07['tags_in_exactly_one_run'])} | {tags(temp00['tags_in_exactly_one_run'])} |

## Latency

| Metric | Temp 0.7 | Temp 0.0 |
| --- | ---: | ---: |
| p50 (ms) | {temp07['latency_ms']['p50']:.3f} | {temp00['latency_ms']['p50']:.3f} |
| p95 (ms) | {temp07['latency_ms']['p95']:.3f} | {temp00['latency_ms']['p95']:.3f} |
| p99 (ms) | {temp07['latency_ms']['p99']:.3f} | {temp00['latency_ms']['p99']:.3f} |

## Interpretation

The fixed input produced {temp07['distinct_tag_sets']} distinct tag set(s) at temperature 0.7 and
{temp00['distinct_tag_sets']} distinct tag set(s) at temperature 0.0. Therefore, two users sending
identical input may receive different but topically valid tags when sampling is enabled, while the
lower temperature should be more repeatable. Variation is acceptable for optional discovery tags,
but it is not acceptable if a safety-critical allergen warning is omitted or changed.
"""


def write_checkpoint(path: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"metadata": metadata, "runs": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_checkpoint(path: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    old = data.get("metadata", {})
    identity_keys = ("model", "input_sha256", "runs_per_temperature")
    if any(old.get(key) != metadata.get(key) for key in identity_keys):
        raise ValueError("Checkpoint settings do not match this experiment; remove the partial file")
    return list(data.get("runs", []))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_id", "temperature", "tags", "summary", "latency_ms", "reviewer_changed",
        "planner_input_tokens", "planner_output_tokens", "reviewer_input_tokens",
        "reviewer_output_tokens",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "tags": json.dumps(row["tags"], ensure_ascii=False)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-file",
        type=Path,
        default=PROJECT_ROOT / "reports/hw01/cases/nondeterminism_input.json",
    )
    parser.add_argument("--runs-per-temperature", type=int, default=20)
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.runs_per_temperature < 1:
        parser.error("--runs-per-temperature must be at least 1")

    title, content = load_input(args.input_file)
    input_bytes = args.input_file.read_bytes()
    started_at = utc_now()
    metadata = {
        "started_at": started_at,
        "model": args.model,
        "base_url": args.base_url,
        "input_file": str(args.input_file.relative_to(PROJECT_ROOT)),
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "runs_per_temperature": args.runs_per_temperature,
        "temperatures": list(TEMPERATURES),
    }

    raw_dir = PROJECT_ROOT / "reports/hw01/raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    partial_path = raw_dir / "nondeterminism_results.partial.json"
    final_json_path = raw_dir / "nondeterminism_results.json"
    final_csv_path = raw_dir / "nondeterminism_results.csv"
    metrics_path = PROJECT_ROOT / "reports/hw01/METRICS.md"
    log_path = PROJECT_ROOT / "reports/hw01/RUN_LOG.txt"
    rows = load_checkpoint(partial_path, metadata) if args.resume else []
    client = OllamaModelClient(model=args.model, base_url=args.base_url)

    with log_path.open("a", encoding="utf-8") as log:
        def record(message: str) -> None:
            line = f"[{utc_now()}] {message}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        record(
            f"START nondeterminism experiment model={args.model} "
            f"runs_per_temperature={args.runs_per_temperature} input_sha256={metadata['input_sha256']}"
        )
        completed = {(float(row["temperature"]), int(row["run_id"])) for row in rows}
        try:
            for temperature in TEMPERATURES:
                for run_id in range(1, args.runs_per_temperature + 1):
                    if (temperature, run_id) in completed:
                        record(f"RESUME skip temperature={temperature} run={run_id}")
                        continue
                    result = run_pipeline(client, title, content, temperature)
                    planner_usage = result["transcript"]["planner"]["usage"]
                    reviewer = result["transcript"]["reviewer"]
                    reviewer_usage = reviewer["usage"]
                    row = {
                        "run_id": run_id,
                        "temperature": temperature,
                        "tags": result["final"]["tags"],
                        "summary": result["final"]["summary"],
                        "latency_ms": result["latency_ms"],
                        "reviewer_changed": reviewer["changed"],
                        "planner_input_tokens": planner_usage["input_tokens"],
                        "planner_output_tokens": planner_usage["output_tokens"],
                        "reviewer_input_tokens": reviewer_usage["input_tokens"],
                        "reviewer_output_tokens": reviewer_usage["output_tokens"],
                    }
                    rows.append(row)
                    write_checkpoint(partial_path, metadata, rows)
                    record(
                        f"RESULT temperature={temperature} run={run_id} "
                        f"latency_ms={row['latency_ms']} tags={json.dumps(row['tags'])}"
                    )
        except (ModelClientError, OSError, ValueError) as exc:
            record(f"FAILED {type(exc).__name__}: {exc}")
            print("Re-run with --resume after correcting the problem.", file=sys.stderr)
            return 1

        completed_at = utc_now()
        metadata["completed_at"] = completed_at
        metrics = {str(temperature): summarize(rows, temperature) for temperature in TEMPERATURES}
        write_checkpoint(final_json_path, metadata, rows)
        write_csv(final_csv_path, rows)
        metrics_path.write_text(make_markdown(metrics, args.model, completed_at), encoding="utf-8")
        if partial_path.exists():
            partial_path.unlink()
        record(f"COMPLETE results={final_json_path.relative_to(PROJECT_ROOT)}")
        print(json.dumps(metrics, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
