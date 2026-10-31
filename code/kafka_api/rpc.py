"""HW8 Part 1 - the request/response client (used by the FastAPI wrapper and by the demo).

make a request:  put {correlation_id, reply_to, operation, data} on s9619_entity_requests,
                 park a future under the correlation_id,
                 a background task reads s9619_entity_responses and completes the matching future.
The correlation_id is created once (by the caller, or here if the caller gave none) and never changed.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Callable, Dict, Optional

from .config import API_GROUP, BOOTSTRAP_SERVERS, REQUEST_TOPIC, RESPONSE_TIMEOUT_S, RESPONSE_TOPIC
from .logutil import log


class KafkaUnavailable(RuntimeError):
    """The broker could not be reached (reported by the API as HTTP 503)."""


def _dump(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


class KafkaRPC:
    def __init__(self, bootstrap: str = BOOTSTRAP_SERVERS, request_topic: str = REQUEST_TOPIC,
                 response_topic: str = RESPONSE_TOPIC, timeout: float = RESPONSE_TIMEOUT_S,
                 producer_factory: Optional[Callable[[], Any]] = None,
                 consumer_factory: Optional[Callable[[], Any]] = None,
                 log_fn: Callable[[str, str], None] = log) -> None:
        self.bootstrap = bootstrap
        self.request_topic = request_topic
        self.response_topic = response_topic
        self.timeout = timeout
        self._producer_factory = producer_factory or self._default_producer
        self._consumer_factory = consumer_factory or self._default_consumer
        self.log = log_fn
        self.producer: Any = None
        self.consumer: Any = None
        self.pending: Dict[str, "asyncio.Future[dict]"] = {}
        self._task: Optional["asyncio.Task[None]"] = None
        self._lock = asyncio.Lock()
        self.started = False

    # ---- default Kafka objects (aiokafka is imported only here)
    def _default_producer(self) -> Any:
        from aiokafka import AIOKafkaProducer
        return AIOKafkaProducer(bootstrap_servers=self.bootstrap)

    def _default_consumer(self) -> Any:
        from aiokafka import AIOKafkaConsumer
        return AIOKafkaConsumer(self.response_topic, bootstrap_servers=self.bootstrap, group_id=API_GROUP,
                                auto_offset_reset="earliest", enable_auto_commit=True)

    # ---- lifecycle
    async def start(self) -> None:
        async with self._lock:
            if self.started:
                return
            producer, consumer = self._producer_factory(), self._consumer_factory()
            try:
                await producer.start()
                await consumer.start()
            except Exception as exc:  # noqa: BLE001
                for closer in (consumer.stop, producer.stop):
                    try:
                        await closer()
                    except Exception:  # noqa: BLE001
                        pass
                raise KafkaUnavailable(f"cannot reach Kafka at {self.bootstrap}: {exc}") from exc
            self.producer, self.consumer = producer, consumer
            self._task = asyncio.create_task(self._consume_responses())
            self.started = True
            self.log("API", f"Kafka client ready: sends to {self.request_topic}, listens on {self.response_topic}")

    async def start_with_retries(self, attempts: int = 40, delay: float = 3.0) -> None:
        """Background start-up: the web app must come up even if Kafka is a few seconds late (or off)."""
        for attempt in range(1, attempts + 1):
            try:
                await self.start()
                return
            except KafkaUnavailable as exc:
                self.log("API", f"Kafka not ready (attempt {attempt}/{attempts}): {exc}")
                await asyncio.sleep(delay)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for closer in (getattr(self.consumer, "stop", None), getattr(self.producer, "stop", None)):
            if closer:
                try:
                    await closer()
                except Exception:  # noqa: BLE001
                    pass
        self.started = False

    # ---- responses
    async def _consume_responses(self) -> None:
        async for msg in self.consumer:
            try:
                data = json.loads(msg.value.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            cid = data.get("correlation_id") if isinstance(data, dict) else None
            future = self.pending.pop(cid, None) if cid else None
            if future is None:
                self.log("API", f"response ignored (nobody waiting) partition={msg.partition} offset={msg.offset} "
                                f"correlation_id={cid}")
                continue
            self.log("API", f"received response topic={msg.topic} partition={msg.partition} offset={msg.offset} "
                            f"correlation_id={cid} message={_dump(data)}")
            if not future.done():
                future.set_result(data)

    # ---- requests
    async def request(self, operation: str, data: Any, correlation_id: Optional[str] = None) -> dict:
        if not self.started:
            await self.start()  # lazy start; raises KafkaUnavailable if the broker is still down
        cid = correlation_id or str(uuid.uuid4())
        message = {"correlation_id": cid, "reply_to": self.response_topic, "operation": operation, "data": data}
        future: "asyncio.Future[dict]" = asyncio.get_running_loop().create_future()
        self.pending[cid] = future
        try:
            meta = await self.producer.send_and_wait(self.request_topic, _dump(message).encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.pending.pop(cid, None)
            raise KafkaUnavailable(f"could not send to Kafka: {exc}") from exc
        self.log("API", f"sent request topic={meta.topic} partition={meta.partition} offset={meta.offset} "
                        f"correlation_id={cid} message={_dump(message)}")
        try:
            response = await asyncio.wait_for(future, timeout=self.timeout)
        except asyncio.TimeoutError:
            self.pending.pop(cid, None)
            self.log("API", f"TIMEOUT after {self.timeout:.0f}s correlation_id={cid}")
            return {"correlation_id": cid, "success": False, "error": "Timeout waiting for the worker's response"}
        self.log("API", f"returning response to the caller correlation_id={cid} success={response.get('success')}")
        return response
