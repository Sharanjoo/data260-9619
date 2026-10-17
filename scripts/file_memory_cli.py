"""HW6 Part 4: chat with the local model using AGENT.md + MEMORY.md as file-based memory.

Commands: /memory  /compact  /dream  /help  /quit   (anything else goes to the model)

    python scripts/file_memory_cli.py                       # interactive
    python scripts/file_memory_cli.py --script FILE         # run the lines of FILE as if typed

For the report, run it through the recorder so your name and timestamps land in RUN_LOG.txt:

    python scripts/recorded_run_hw06.py -- python scripts/file_memory_cli.py --script scripts/file_memory_demo_commands.txt
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.file_memory import FileMemorySession  # noqa: E402
from src.model_client import ModelClientError, OllamaModelClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent", type=Path, default=ROOT / "AGENT.md")
    parser.add_argument("--memory", type=Path, default=ROOT / "MEMORY.md")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--script", type=Path, help="read the input lines from this file instead of the keyboard")
    parser.add_argument("--no-startup-check", action="store_true", help="skip the automatic consolidation check")
    args = parser.parse_args()

    client = OllamaModelClient(model=args.model, base_url=args.base_url, timeout_seconds=900)
    session = FileMemorySession(client, args.agent, args.memory)
    print("File-based memory chat - Sharan Lourduraj (SID4 9619)")
    print(f"model={args.model}  AGENT.md={args.agent.name}  MEMORY.md={args.memory.name}\n")
    try:
        if not args.no_startup_check:
            print(session.startup_check() + "\n")
        lines = (
            [ln.strip() for ln in args.script.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
            if args.script
            else None
        )
        index = 0
        while True:
            if lines is not None:
                if index >= len(lines):
                    break
                text = lines[index]
                index += 1
                print(f"you> {text}")
            else:
                try:
                    text = input("you> ").strip()
                except EOFError:
                    break
                if not text:
                    continue
            if text == "/quit":
                break
            started = time.perf_counter()
            reply = session.handle(text)
            print(f"{'assistant> ' if not text.startswith('/') else ''}{reply}")
            print(f"[{time.perf_counter() - started:.1f} s]\n")
    except ModelClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
