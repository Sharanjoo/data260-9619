"""HW8 Part 1 - configuration: Section 0 values, topic names and Kafka settings.

Two PREFIX-prefixed topics carry the whole request/response service:
    s9619_entity_requests    the API wrapper (client) sends requests here, the worker reads them
    s9619_entity_responses   the worker sends responses here, the API wrapper reads them
"""
from __future__ import annotations

import os

SID4 = "9619"
PORT_BASE = 8619
PREFIX = f"s{SID4}"
SEED = 9619
VERIFY_SEED = 260000 + 9619

REQUEST_TOPIC = f"{PREFIX}_entity_requests"
RESPONSE_TOPIC = f"{PREFIX}_entity_responses"

# Inside Docker the broker is reachable as kafka:19092 (compose sets the variable);
# from the laptop (homework scripts) it is localhost:49092.
BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:49092")

WORKER_GROUP = f"{PREFIX}-entity-worker"
API_GROUP = f"{PREFIX}-fastapi-response-group"
RESPONSE_TIMEOUT_S = float(os.environ.get("HW8_RPC_TIMEOUT", "15"))

# Entity: Grocery Recall Notice (DOMAIN_ID 3, see DOMAIN_SCHEMA.md)
OPERATIONS = ("CREATE_RECALL_NOTICE", "GET_RECALL_NOTICE")
CATEGORIES = ("food-safety-recall", "allergen-alert", "quality-withdrawal", "supply-shortage")
