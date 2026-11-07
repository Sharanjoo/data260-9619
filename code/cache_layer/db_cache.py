"""HW9 Part 1: a Redis view counter in front of the MySQL recall_record table.

The class holds a Redis client and a SQLAlchemy session factory. increment_recall_record_views() is the one new
method the assignment asks for: INCR in Redis on every access, copy the count into MySQL on every 10th access."""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import redis
from sqlalchemy import text

from cache_layer.config import PREFIX, REDIS_HOST, REDIS_PORT, VIEWS_SYNC_EVERY

log = logging.getLogger("hw9.views")


class RecallDatabaseWithCache:
    def __init__(self, redis_client: Optional[redis.Redis] = None,
                 session_factory: Optional[Callable[[], Any]] = None) -> None:
        self.redis_client = redis_client or redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        if session_factory is None:
            from db import SessionLocal  # code/db.py (MySQL s9619_rel); imported late so tests can pass their own
            session_factory = SessionLocal
        self.session_factory = session_factory

    @staticmethod
    def views_key(recall_record_id: int) -> str:
        return f"{PREFIX}:views:recall_record:{recall_record_id}"

    def increment_recall_record_views(self, recall_record_id: int) -> int:
        """Count one access of a recall record. Returns the current total."""
        key = self.views_key(recall_record_id)
        count = self.redis_client.incr(key)  # atomic in Redis, so concurrent requests never lose a view
        if count % VIEWS_SYNC_EVERY == 0:
            with self.session_factory() as session:
                updated = session.execute(
                    text("UPDATE recall_record SET view_count = :n WHERE id = :id"),
                    {"n": count, "id": recall_record_id}).rowcount
                session.commit()
            if updated:
                log.info("Synced views to database (recall_record %s = %s)", recall_record_id, count)
            else:
                log.warning("No recall_record %s in the database; count %s stays only in Redis",
                            recall_record_id, count)
        return count
