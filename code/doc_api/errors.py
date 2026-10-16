"""HW6 Part 1 - error handling.

* Validation failures on the HW6 routes become a clear, flat 422 body.
  Requests to every other route keep FastAPI's default 422 format, so the HW5
  behaviour (and its Postman screenshots) is unchanged.
* Database problems become JSON errors: 503 when MongoDB cannot be reached,
  422 when MongoDB's own schema validator rejects a write, 500 otherwise.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import ConnectionFailure, PyMongoError, WriteError

from .config import API_PREFIX

MONGO_SCHEMA_VALIDATION_FAILED = 121


async def notice_validation_handler(request: Request, exc: RequestValidationError):
    if not request.url.path.startswith(API_PREFIX):
        return await request_validation_exception_handler(request, exc)
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ())]
        # A JSON syntax error reports a character position as its "field": drop it.
        is_json_error = err.get("type") == "json_invalid"
        details.append(
            {
                "location": loc[0] if loc else "body",
                "field": "" if is_json_error else (".".join(loc[1:]) if len(loc) > 1 else ""),
                "message": err.get("msg", "invalid value"),
                "type": err.get("type", "value_error"),
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_failed",
            "message": f"{len(details)} validation error(s): the request was not saved",
            "details": details,
        },
    )


async def pymongo_error_handler(request: Request, exc: PyMongoError):
    if isinstance(exc, ConnectionFailure):  # includes ServerSelectionTimeoutError
        return JSONResponse(
            status_code=503,
            content={"error": "database_unavailable", "message": "MongoDB could not be reached; try again shortly"},
        )
    if isinstance(exc, WriteError) and exc.code == MONGO_SCHEMA_VALIDATION_FAILED:
        return JSONResponse(
            status_code=422,
            content={"error": "schema_validation_failed", "message": "MongoDB rejected the document: it violates the collection's validation rules"},
        )
    return JSONResponse(
        status_code=500,
        content={"error": "database_error", "message": "An unexpected database error occurred"},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, notice_validation_handler)
    app.add_exception_handler(PyMongoError, pymongo_error_handler)
