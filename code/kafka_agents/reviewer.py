"""Reviewer agent: reads s9619_drafts, writes s9619_final (status + answer).   python code/kafka_agents/reviewer.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kafka_agents.runtime import main_for  # noqa: E402
from kafka_agents.stages import make_reviewer  # noqa: E402

if __name__ == "__main__":
    main_for(make_reviewer)
