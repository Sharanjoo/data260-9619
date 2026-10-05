"""Run a command and append its real, timestamped console output to
reports/hw05/RUN_LOG.txt (and echo it to the terminal as it runs).

Usage (from the repo root):
    python scripts/recorded_run_hw05.py -- python scripts/test_execute_tool_hw05.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "reports/hw05/RUN_LOG.txt"
STUDENT = "Sharan Lourduraj"
HEADER = f"HW5 RUN_LOG - {STUDENT}, SID4 9619, DOMAIN_ID 3 (Grocery Recall Notice)\n" + "=" * 70 + "\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("provide a command after --")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_PATH.exists() or LOG_PATH.stat().st_size == 0
    with LOG_PATH.open("a", encoding="utf-8") as log:
        if new_file:
            log.write(HEADER)
        banner = f"\n[{utc_now()}] {STUDENT} | START command: {' '.join(command)}"
        print(banner)
        log.write(banner + "\n")
        # -u so a child Python process streams output line by line
        if command[0] in ("python", "python3", sys.executable) and "-u" not in command[:2]:
            command = [command[0], "-u", *command[1:]]
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log.write(line)
        code = process.wait()
        end = f"[{utc_now()}] END exit_code={code}"
        print(end)
        log.write(end + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
