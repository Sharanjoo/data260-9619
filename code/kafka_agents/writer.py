"""Writer agent: reads s9619_tasks (plans), writes s9619_drafts.
   python code/kafka_agents/writer.py [--instance A]   (start a second one with --instance B to share the partitions)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kafka_agents.runtime import main_for  # noqa: E402
from kafka_agents.stages import make_writer  # noqa: E402

if __name__ == "__main__":
    main_for(make_writer, instance_arg=True)
