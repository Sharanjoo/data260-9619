"""HW9 Part 2: the Redis side of the semantic cache.

Each cached answer is one Redis hash  s9619:cache:<sha1 of the query>  with the fields
    query, embedding (384 float32), answer, depends_on, data_version, created_at
and a RediSearch index (s9619_cache_idx, FLAT vector field, COSINE) over that prefix. lookup() asks Redis for the single
nearest stored query (KNN 1) and returns it together with its cosine similarity (1 - cosine distance); the caller
compares that number with the threshold, so the same lookup serves every threshold in the Part 3 sweep."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from redis.exceptions import ResponseError

from cache_layer.config import CACHE_INDEX, CACHE_KEY_PREFIX, EMBED_DIM, NO_DEPENDENCY


def entry_key(query: str) -> str:
    return CACHE_KEY_PREFIX + hashlib.sha1(query.strip().encode("utf-8")).hexdigest()[:16]


class SemanticCache:
    def __init__(self, redis_client: Any) -> None:
        self.r = redis_client

    # ------------------------------------------------------------------ index
    def ensure_index(self) -> bool:
        """Create the vector index if it does not exist. Returns True when it was created now."""
        try:
            self.r.ft(CACHE_INDEX).info()
            return False
        except ResponseError:
            pass
        schema = (
            TextField("query"),
            TagField("depends_on"),
            VectorField("embedding", "FLAT", {"TYPE": "FLOAT32", "DIM": EMBED_DIM, "DISTANCE_METRIC": "COSINE"}),
        )
        self.r.ft(CACHE_INDEX).create_index(
            schema, definition=IndexDefinition(prefix=[CACHE_KEY_PREFIX], index_type=IndexType.HASH))
        return True

    def clear(self) -> int:
        """Delete every cached entry (only keys under this homework's cache prefix)."""
        keys = list(self.r.scan_iter(match=CACHE_KEY_PREFIX + "*", count=500))
        return self.r.delete(*keys) if keys else 0

    def size(self) -> int:
        return sum(1 for _ in self.r.scan_iter(match=CACHE_KEY_PREFIX + "*", count=500))

    # ------------------------------------------------------------------ read / write
    def lookup(self, embedding: bytes) -> tuple[Optional[dict], float]:
        """The nearest stored query and its cosine similarity; (None, 0.0) when the cache is empty."""
        q = (Query("*=>[KNN 1 @embedding $vec AS dist]")
             .sort_by("dist").return_fields("query", "answer", "depends_on", "data_version", "created_at", "dist")
             .dialect(2))
        res = self.r.ft(CACHE_INDEX).search(q, query_params={"vec": embedding})
        if not res.docs:
            return None, 0.0
        doc = res.docs[0]
        entry = {"key": doc.id, "query": doc.query, "answer": doc.answer, "depends_on": doc.depends_on,
                 "data_version": doc.data_version, "created_at": doc.created_at}
        return entry, round(1.0 - float(doc.dist), 6)

    def store(self, query: str, embedding: bytes, answer: str, data_version: str = NO_DEPENDENCY,
              depends_on: str = NO_DEPENDENCY) -> str:
        key = entry_key(query)
        self.r.hset(key, mapping={
            "query": query, "embedding": embedding, "answer": answer, "depends_on": depends_on,
            "data_version": data_version, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return key

    def delete(self, key: str) -> int:
        return self.r.delete(key)
