"""HW8 test support: a tiny in-memory stand-in for the parts of aiokafka the homework code uses.

Only for the offline tests (scripts/test_*_hw08.py). It keeps topics with partitions, per-group committed
offsets and a key -> partition rule, so the same worker/client code that talks to real Kafka runs unchanged.
The real-Kafka runs (docker compose) are the proof for Kafka itself; this checks OUR logic fast and offline.
"""
from __future__ import annotations

import asyncio
import zlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Record:
    topic: str
    partition: int
    offset: int
    key: Optional[bytes]
    value: bytes
    timestamp: int = 0


@dataclass
class Meta:
    topic: str
    partition: int
    offset: int
    timestamp: int = 0


class FakeBroker:
    def __init__(self) -> None:
        self.topics: Dict[str, List[List[Record]]] = {}
        self.committed: Dict[Tuple[str, str, int], int] = {}
        self._rr: Dict[str, int] = {}
        self._clock = 0

    def create_topic(self, name: str, partitions: int = 1) -> None:
        self.topics.setdefault(name, [[] for _ in range(partitions)])

    def produce(self, topic: str, value: bytes, key: Optional[bytes] = None) -> Meta:
        self.create_topic(topic)
        parts = self.topics[topic]
        if key is not None:
            p = zlib.crc32(key) % len(parts)
        else:
            p = self._rr.get(topic, 0) % len(parts)
            self._rr[topic] = p + 1
        self._clock += 1
        rec = Record(topic, p, len(parts[p]), key, value, self._clock)
        parts[p].append(rec)
        return Meta(topic, p, rec.offset, self._clock)

    def all_values(self, topic: str) -> List[bytes]:
        return [r.value for part in self.topics.get(topic, []) for r in part]


class FakeProducer:
    def __init__(self, broker: FakeBroker) -> None:
        self.broker = broker
        self.sent: List[Meta] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_and_wait(self, topic: str, value: bytes, key: Optional[bytes] = None, **_: object) -> Meta:
        meta = self.broker.produce(topic, value, key)
        self.sent.append(meta)
        return meta


class FakeConsumer:
    """Async iterator over one topic for one consumer group (all partitions of the topic)."""

    def __init__(self, broker: FakeBroker, topic: str, group: str, partitions: Optional[List[int]] = None) -> None:
        self.broker, self.topic, self.group = broker, topic, group
        self.only = partitions  # stands in for the group's partition assignment (None = every partition)
        self.broker.create_topic(topic)
        self.closed = False
        self.position: Dict[int, int] = {}
        self.delivered = 0
        self.commits = 0

    async def start(self) -> None:
        for p in self._mine():
            self.position[p] = self.broker.committed.get((self.group, self.topic, p), 0)

    def _mine(self) -> List[int]:
        n = len(self.broker.topics[self.topic])
        return list(range(n)) if self.only is None else [p for p in self.only if p < n]

    async def stop(self) -> None:
        self.closed = True

    def __aiter__(self) -> "FakeConsumer":
        return self

    async def __anext__(self) -> Record:
        while True:
            if self.closed:
                raise StopAsyncIteration
            for p in self._mine():
                part = self.broker.topics[self.topic][p]
                pos = self.position.get(p, 0)
                if pos < len(part):
                    self.position[p] = pos + 1
                    self.delivered += 1
                    return part[pos]
            await asyncio.sleep(0.002)

    async def commit(self) -> None:
        for p, pos in self.position.items():
            self.broker.committed[(self.group, self.topic, p)] = pos
        self.commits += 1
