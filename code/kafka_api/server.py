"""HW8 Part 1 - the FastAPI wrapper: HTTP in, Kafka request/response underneath.

`install(app)` is what code/main.py calls, so the routes share the one server on PORT_BASE (8619).

    POST /api/hw8/requests            {operation, data, correlation_id?}  -> the worker's response, unchanged
    POST /api/hw8/recall-notices      body = recall notice fields          -> CREATE_RECALL_NOTICE through Kafka
    GET  /api/hw8/recall-notices/{id}                                      -> GET_RECALL_NOTICE through Kafka
    POST /api/hw8/direct              {operation, data}                    -> same logic, NO Kafka (JMeter baseline)
    GET  /api/hw8/health                                                   -> is the Kafka client connected?
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from .config import PORT_BASE, REQUEST_TOPIC, RESPONSE_TOPIC
from .entity_logic import RecallNoticeStore
from .logutil import log
from .rpc import KafkaRPC, KafkaUnavailable

router = APIRouter(prefix="/api/hw8", tags=["hw8-kafka"])
rpc = KafkaRPC()
direct_store = RecallNoticeStore(idempotent=False)  # the baseline keeps its own notices, not shared with the worker


def _status_for(operation: str, response: Dict[str, Any]) -> int:
    if response.get("success"):
        return 201 if operation == "CREATE_RECALL_NOTICE" else 200
    error = str(response.get("error", ""))
    if error.endswith("not found"):
        return 404
    if error.startswith("Timeout"):
        return 504
    return 422


async def _via_kafka(operation: Any, data: Any, correlation_id: Any = None) -> JSONResponse:
    if not isinstance(operation, str) or not operation:
        return JSONResponse(status_code=422, content={"correlation_id": correlation_id, "success": False,
                                                      "error": "operation is required"})
    if correlation_id is not None and not isinstance(correlation_id, str):
        return JSONResponse(status_code=422, content={"correlation_id": None, "success": False,
                                                      "error": "correlation_id must be text"})
    try:
        response = await rpc.request(operation, data, correlation_id)
    except KafkaUnavailable as exc:
        return JSONResponse(status_code=503, content={"correlation_id": correlation_id, "success": False,
                                                      "error": f"Kafka unavailable: {exc}"})
    return JSONResponse(status_code=_status_for(operation, response), content=response)


@router.post("/requests")
async def kafka_request(payload: dict):
    return await _via_kafka(payload.get("operation"), payload.get("data", {}), payload.get("correlation_id"))


@router.post("/recall-notices")
async def create_recall_notice(payload: dict):
    return await _via_kafka("CREATE_RECALL_NOTICE", payload)


@router.get("/recall-notices/{recall_notice_id}")
async def get_recall_notice(recall_notice_id: str):
    return await _via_kafka("GET_RECALL_NOTICE", {"recall_notice_id": recall_notice_id})


@router.post("/direct")
async def direct(payload: dict):
    """The same validation and storage as the worker, called as a plain function: the JMeter baseline."""
    operation = payload.get("operation")
    response = direct_store.handle({"correlation_id": payload.get("correlation_id") or str(uuid.uuid4()),
                                    "operation": operation, "data": payload.get("data", {})})
    return JSONResponse(status_code=_status_for(str(operation), response), content=response)


@router.get("/health")
async def kafka_health():
    return {"kafka_client_ready": rpc.started, "request_topic": REQUEST_TOPIC, "response_topic": RESPONSE_TOPIC}


def install(app: FastAPI) -> None:
    app.include_router(router)

    @app.on_event("startup")
    async def _hw8_start() -> None:
        asyncio.create_task(rpc.start_with_retries())  # never block (or break) the other homeworks' routes
        log("API", f"FastAPI server started at http://127.0.0.1:{PORT_BASE} (HW8 Kafka routes under /api/hw8)")

    @app.on_event("shutdown")
    async def _hw8_stop() -> None:
        await rpc.stop()
