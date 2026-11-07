"""HW9 Part 2: send one question into the HW8 pipeline (s9619_inbox) and wait for the answer on s9619_final.

Reuses the HW8 client (kafka_agents.send_question.ask): same topics, same correlation_id handling. The Planner, Writer
and Reviewer must be running (three terminals, as in HW8)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from kafka_api.config import BOOTSTRAP_SERVERS
from kafka_agents.send_question import ask as kafka_ask
from kafka_agents.settings import FINAL_TOPIC

from cache_layer.config import AGENT_TIMEOUT_S


class AgentClient:
    def __init__(self) -> None:
        self.producer: Any = None
        self.consumer: Any = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        self.consumer = AIOKafkaConsumer(FINAL_TOPIC, bootstrap_servers=BOOTSTRAP_SERVERS,
                                         group_id=f"s9619-hw9-client-{uuid.uuid4().hex[:8]}",
                                         auto_offset_reset="earliest", enable_auto_commit=False)
        self.producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP_SERVERS)
        await self.consumer.start()
        await self.producer.start()

    async def stop(self) -> None:
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def run(self, question: str, correlation_id: str, entity_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """The final message for this correlation_id (status, answer, ...), or None on timeout."""
        return await kafka_ask(self.producer, self.consumer, question, correlation_id, entity_key, AGENT_TIMEOUT_S)
