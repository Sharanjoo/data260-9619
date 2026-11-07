"""HW9 Part 1 offline checks (python scripts/test_hw9_part1.py).

Uses the real Redis on 127.0.0.1:46379 when it is up (docker compose up -d redis); otherwise a tiny in-memory
stand-in and says so (a stand-in is not evidence about Redis, only about this class). The database is a temporary
SQLite table with the columns the method touches, so no MySQL is needed. The real MySQL + Redis run is
scripts/hw9_part1_counter.py."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

sys.modules.setdefault("db", types.ModuleType("db"))  # code/db.py would open a MySQL engine; not needed here
from cache_layer.config import PREFIX, REDIS_HOST, REDIS_PORT  # noqa: E402
from cache_layer.db_cache import RecallDatabaseWithCache  # noqa: E402

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


class StandIn:
    """Only incr/get/delete/keys, guarded by a lock like Redis's single thread."""

    def __init__(self) -> None:
        self.d: dict = {}
        self.lock = threading.Lock()

    def incr(self, key):
        with self.lock:
            self.d[key] = int(self.d.get(key, 0)) + 1
            return self.d[key]

    def get(self, key):
        return self.d.get(key)

    def delete(self, *keys):
        with self.lock:
            return sum(self.d.pop(k, None) is not None for k in keys)


def make_redis():
    import redis
    try:
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        client.ping()
        return client, f"real Redis {REDIS_HOST}:{REDIS_PORT}"
    except Exception:  # noqa: BLE001
        return StandIn(), "in-memory stand-in (Redis not reachable)"


def make_db(ids):
    """A temporary SQLite file (every thread gets its own connection, like separate requests to MySQL)."""
    path = os.path.join(tempfile.mkdtemp(prefix="hw9_part1_"), "t.db")
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})
    with engine.begin() as c:
        c.execute(text("CREATE TABLE recall_record (id INTEGER PRIMARY KEY, view_count INTEGER NOT NULL DEFAULT 0)"))
        for i in ids:
            c.execute(text("INSERT INTO recall_record (id) VALUES (:i)"), {"i": i})
    return sessionmaker(bind=engine), engine


def db_value(engine, rid):
    with engine.connect() as c:
        return c.execute(text("SELECT view_count FROM recall_record WHERE id = :i"), {"i": rid}).scalar()


def main() -> int:
    client, label = make_redis()
    print(f"redis: {label}")
    rid = 990001  # test ids stay clear of real records; only keys s9619:views:recall_record:99* are touched
    sessions, engine = make_db([rid, rid + 1])
    store = RecallDatabaseWithCache(redis_client=client, session_factory=sessions)
    key = store.views_key(rid)
    client.delete(key, store.views_key(rid + 1))

    check("key starts with the PREFIX", key == f"{PREFIX}:views:recall_record:{rid}" and key.startswith(PREFIX + ":"), key)

    totals = [store.increment_recall_record_views(rid) for _ in range(25)]
    check("25 accesses return 1..25 in order", totals == list(range(1, 26)))
    check("Redis holds 25", int(client.get(key)) == 25)
    check("database holds 20 (last sync at access 20)", db_value(engine, rid) == 20, f"{db_value(engine, rid)}")

    client.delete(key)
    with engine.begin() as c:
        c.execute(text("UPDATE recall_record SET view_count = 0 WHERE id = :i"), {"i": rid})
    seen = []
    for n in range(1, 22):
        store.increment_recall_record_views(rid)
        seen.append((n, db_value(engine, rid)))
    check("no sync before access 10", all(v == 0 for n, v in seen if n < 10))
    check("sync happens at access 10", dict(seen)[10] == 10)
    check("no extra sync at access 11-19", all(v == 10 for n, v in seen if 10 <= n < 20))
    check("sync happens at access 20, none at 21", dict(seen)[20] == 20 and dict(seen)[21] == 20)

    other = store.increment_recall_record_views(rid + 1)
    check("another record counts separately", other == 1 and int(client.get(key)) == 21)

    missing = 990099
    client.delete(store.views_key(missing))
    for _ in range(10):
        count = store.increment_recall_record_views(missing)
    check("a record that is not in the database still counts and does not raise", count == 10)
    client.delete(store.views_key(missing))

    # concurrency: 20 threads x 25 accesses of one record. INCR is atomic, so no view may be lost in Redis. The
    # database copy is only a snapshot written on every 10th access: two syncs can arrive out of order, so it is
    # checked for "a multiple of 10 that is at most the Redis count", not for equality (see Known Limits).
    client.delete(key)
    with engine.begin() as c:
        c.execute(text("UPDATE recall_record SET view_count = 0 WHERE id = :i"), {"i": rid})
    results: list[int] = []
    lock = threading.Lock()

    def work() -> None:
        mine = [store.increment_recall_record_views(rid) for _ in range(25)]
        with lock:
            results.extend(mine)

    threads = [threading.Thread(target=work) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    check("500 concurrent accesses: every total 1..500 handed out exactly once", sorted(results) == list(range(1, 501)))
    check("Redis holds 500", int(client.get(key)) == 500)
    final_db = db_value(engine, rid)
    check("database holds a synced multiple of 10 that is at most 500", final_db % 10 == 0 and 0 < final_db <= 500,
          f"database ended at {final_db} (Redis 500)")

    client.delete(key, store.views_key(rid + 1))
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
