"""HW4 Part 2: MySQL-backed CRUD for the primary domain entity, plus
email+password login backed by server-side sessions (opaque cookie token
only -- the session record itself lives in MySQL).

Mounted into the same FastAPI app as auth.py's HW3 routes and main.py's
original /api/notices routes -- this file adds new routes, it does not
touch either of those.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session, joinedload

from db import RecallRecord, RecallSource, User, UserSession, get_db

router = APIRouter(prefix="/api/hw4")

SESSION_COOKIE_NAME = "hw4_session"
SESSION_TTL_HOURS = 24

# Schemas
class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RecordIn(BaseModel):
    product_name: str = Field(..., min_length=1)
    brand_name: str = Field(..., min_length=1)


class RecordOut(BaseModel):
    id: int
    product_name: str
    brand_name: str
    source_name: Optional[str] = None
    source_region: Optional[str] = None

    class Config:
        from_attributes = True


def _to_record_out(rec: RecallRecord) -> RecordOut:
    return RecordOut(
        id=rec.id,
        product_name=rec.product_name,
        brand_name=rec.brand_name,
        source_name=rec.source.source_name if rec.source else None,
        source_region=rec.source.source_region if rec.source else None,
    )


# Auth: server-side sessions, opaque cookie token only
def _hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Login required")

    sess = db.get(UserSession, token)
    if not sess or sess.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=401, detail="Login required")

    user = db.get(User, sess.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user


@router.post("/auth/register", status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(name=payload.name, email=payload.email, password_hash=_hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "name": user.name, "email": user.email}


@router.post("/auth/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)
    db.add(UserSession(id=token, user_id=user.id, expires_at=expires_at))
    db.commit()

    # Opaque token only -- no user data in the cookie itself.
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,       # works on http://localhost (secure-context exception)
        samesite="none",   # React dev server runs on a different port (cross-site)
        max_age=SESSION_TTL_HOURS * 3600,
    )
    return {"id": user.id, "name": user.name, "email": user.email}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        sess = db.get(UserSession, token)
        if sess:
            db.delete(sess)
            db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "logged out"}


@router.get("/auth/me")
def me(user: User = Depends(require_user)):
    return {"id": user.id, "name": user.name, "email": user.email}


# CRUD for the primary domain entity (recall_record), gated on login
@router.post("/records", response_model=RecordOut, status_code=201)
def create_record(payload: RecordIn, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    rec = RecallRecord(product_name=payload.product_name.strip(), brand_name=payload.brand_name.strip())
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return _to_record_out(rec)


@router.get("/records", response_model=List[RecordOut])
def list_records_naive(
    limit: Optional[int] = Query(default=None, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_user),
):
    """Deliberately naive (Part 3): one extra query per record to load its
    related source -- SQLAlchemy lazy-loads rec.source on each access below."""
    q = db.query(RecallRecord).order_by(RecallRecord.id).offset(offset)
    if limit is not None:
        q = q.limit(limit)
    records = q.all()
    return [_to_record_out(r) for r in records]  # each _to_record_out() touches rec.source -> 1 query/row


@router.get("/records/{record_id}", response_model=RecordOut)
def get_record(record_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    rec = db.get(RecallRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    return _to_record_out(rec)


@router.put("/records/{record_id}", response_model=RecordOut)
def update_record(record_id: int, payload: RecordIn, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    rec = db.get(RecallRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    rec.product_name = payload.product_name.strip()
    rec.brand_name = payload.brand_name.strip()
    db.commit()
    db.refresh(rec)
    return _to_record_out(rec)


@router.delete("/records/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    rec = db.get(RecallRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")
    db.delete(rec)
    db.commit()
    return {"message": f"Record {record_id} deleted"}


# Part 3: the "fixed" counterpart to GET /records -- single JOIN query instead
# of N+1. Same auth gate, same response shape, so the two are directly comparable.
@router.get("/records-fixed", response_model=List[RecordOut])
def list_records_fixed(
    limit: Optional[int] = Query(default=None, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_user),
):
    q = (
        db.query(RecallRecord)
        .options(joinedload(RecallRecord.source))
        .order_by(RecallRecord.id)
        .offset(offset)
    )
    if limit is not None:
        q = q.limit(limit)
    records = q.all()
    return [_to_record_out(r) for r in records]
