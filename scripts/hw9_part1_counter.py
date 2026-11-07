"""HW9 Part 1 demo: 25 accesses of one recall record through the Redis view counter.

    python scripts/hw9_part1_counter.py                     (the lowest record id in the table, 25 accesses)
    python scripts/hw9_part1_counter.py --record-id 7 --accesses 25

The counter key is reset first (only that one key), so the run always starts at 0. At the end it shows the value in
Redis next to the value in MySQL: they differ by the accesses since the last sync, which is the cost of syncing
every 10th access instead of every access."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from cache_layer.config import BANNER  # noqa: E402
from cache_layer.db_cache import RecallDatabaseWithCache  # noqa: E402
from sqlalchemy import text  # noqa: E402


class Pending(logging.Handler):
    """Collects the 'Synced views to database' log lines so they print right after the access line that caused them."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-id", type=int, default=None, help="default: the lowest id in recall_record")
    parser.add_argument("--accesses", type=int, default=25)
    args = parser.parse_args()

    print(BANNER + " | hw9_part1_counter", flush=True)
    store = RecallDatabaseWithCache()
    pending = Pending()
    logging.getLogger("hw9.views").addHandler(pending)
    logging.getLogger("hw9.views").setLevel(logging.INFO)

    if args.record_id is None:
        with store.session_factory() as session:
            args.record_id = session.execute(text("SELECT MIN(id) FROM recall_record")).scalar()
        if args.record_id is None:
            print("recall_record is empty")
            return 1
    key = store.views_key(args.record_id)
    store.redis_client.delete(key)
    with store.session_factory() as session:
        row = session.execute(text("SELECT product_name, brand_name, record_code FROM recall_record WHERE id = :i"),
                              {"i": args.record_id}).first()
        if row is None:
            print(f"no recall_record with id {args.record_id}")
            return 1
        session.execute(text("UPDATE recall_record SET view_count = 0 WHERE id = :i"), {"i": args.record_id})
        session.commit()
    print(f"record {args.record_id}: {row.product_name} / {row.brand_name} ({row.record_code})   redis key: {key}\n")

    print("=== Testing Counter ===\n")
    for n in range(1, args.accesses + 1):
        total = store.increment_recall_record_views(args.record_id)
        print(f"Access #{n}: Total = {total}")
        while pending.lines:
            pending.lines.pop(0)
            print("✓ Synced views to database")

    with store.session_factory() as session:
        in_db = session.execute(text("SELECT view_count FROM recall_record WHERE id = :i"),
                                {"i": args.record_id}).scalar()
    in_redis = int(store.redis_client.get(key))
    print(f"\nRedis {key} = {in_redis}")
    print(f"MySQL recall_record.view_count = {in_db}   (not yet synced: {in_redis - in_db})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
