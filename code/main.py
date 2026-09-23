"""FastAPI backend for the Grocery Recall Notice app (Homework 2 & 3)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
import os
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router
from fastapi.middleware.cors import CORSMiddleware
import time
from db import get_query_count, init_db, reset_query_counter
from db_routes import router as db_router

PORT_BASE = 8619
WEB_DIR = Path(__file__).resolve().parent / "web_application"

app = FastAPI(title="Grocery Recall Notice API", version="3.0.0")

# HW3 Part 1: session middleware for the auth system.
# SESSION_SECRET_KEY should come from an environment variable in a real deployment;
# the fallback here is only for local homework demo use.
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "hw3-dev-secret-9619-change-me")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="hw3_session",
    max_age=86400,       # 24h absolute ceiling
    same_site="lax",
    https_only=True,      # sets the Secure flag — works on http://localhost
)

app.include_router(auth_router)

# HW4 Part 1/2: allow the Vite React client (different port = cross-origin)
# to send/receive the HttpOnly session cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def sql_query_count_and_timing(request, call_next):
    """HW4 Part 3: counts SQL statements per request (X-SQL-Query-Count) and
    server-side processing time (X-Process-Time-Ms), for the N+1 measurement script."""
    reset_query_counter()
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    response.headers["X-SQL-Query-Count"] = str(get_query_count())
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.3f}"
    return response


app.include_router(db_router)


@app.on_event("startup")
def _init_mysql_with_retry():
    """MySQL's container can take a few seconds longer than the app to accept
    connections; retry briefly instead of crashing the app on a cold compose up."""
    last_err = None
    for attempt in range(10):
        try:
            init_db()
            print("HW4 Part 2: MySQL schema ready (s9619_rel).")
            return
        except Exception as exc:  # noqa: BLE001 - genuinely want to catch+retry any DB error here
            last_err = exc
            time.sleep(2)
    print(f"HW4 Part 2 WARNING: could not initialize MySQL after retries: {last_err}")


class RecallNotice(BaseModel):
    id: int
    productName: str
    brandName: str
    submitterEmail: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    submissionDate: str


class NoticeCreate(BaseModel):
    productName: str = Field(..., min_length=1)
    brandName: str = Field(..., min_length=1)
    submitterEmail: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


class NoticeUpdate(BaseModel):
    productName: str = Field(..., min_length=1)
    brandName: str = Field(..., min_length=1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


notices: List[RecallNotice] = [
    RecallNotice(
        id=1,
        productName="Value Brand Peanut Butter",
        brandName="GreenAcre Foods",
        submitterEmail="qa@greenacre.example",
        description=(
            "Undeclared peanut traces detected in retail packaging; consumers "
            "with peanut allergies should discard the product."
        ),
        category="allergen-alert",
        submissionDate=_now_iso(),
    ),
    RecallNotice(
        id=2,
        productName="Frozen Mixed Berries",
        brandName="Northfield Farms",
        submitterEmail="safety@northfield.example",
        description=(
            "Possible Hepatitis A contamination identified in a recent lot; do "
            "not consume and return to point of purchase for a refund."
        ),
        category="food-safety-recall",
        submissionDate=_now_iso(),
    ),
]


@app.get("/api/health")
async def health():
    return {"status": "ok", "port": PORT_BASE}


@app.get("/api/notices", response_model=List[RecallNotice])
async def list_notices(
    response: Response,
    q: Optional[str] = Query(default=None, description="Filter by product name or brand"),
):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    if not q or not q.strip():
        return notices
    needle = q.strip().lower()
    return [
        n for n in notices
        if needle in n.productName.lower() or needle in n.brandName.lower()
    ]


@app.post("/api/notices", response_model=RecallNotice, status_code=201)
async def create_notice(payload: NoticeCreate):
    new_id = max((n.id for n in notices), default=0) + 1
    notice = RecallNotice(
        id=new_id,
        productName=payload.productName.strip(),
        brandName=payload.brandName.strip(),
        submitterEmail=payload.submitterEmail,
        description=payload.description,
        category=payload.category,
        submissionDate=_now_iso(),
    )
    notices.append(notice)
    print(f"Created notice: {notice}")
    return notice


@app.put("/api/notices/{notice_id}", response_model=RecallNotice)
async def update_notice(notice_id: int, payload: NoticeUpdate):
    for index, notice in enumerate(notices):
        if notice.id == notice_id:
            updated = notice.model_copy(update={
                "productName": payload.productName.strip(),
                "brandName": payload.brandName.strip(),
            })
            notices[index] = updated
            print(f"Updated notice {notice_id}: {updated}")
            return updated
    raise HTTPException(status_code=404, detail=f"Notice {notice_id} not found")


@app.delete("/api/notices/highest", response_model=RecallNotice)
async def delete_highest_notice():
    if not notices:
        raise HTTPException(status_code=404, detail="No notices to delete")
    highest = max(notices, key=lambda n: n.id)
    notices.remove(highest)
    print(f"Deleted highest-ID notice: {highest}")
    return highest

# Old HW1/HW2 static SPA moved off "/" to make room for the HW3 home page.
app.mount("/recalls-app", StaticFiles(directory=str(WEB_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT_BASE)