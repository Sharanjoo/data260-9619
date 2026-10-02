"""HW4 Part 2 / HW5 Part 1.II: MySQL-backed CRUD for the primary domain
entity and its related entity, plus email+password login backed by
server-side sessions (opaque cookie token only -- the session record itself
lives in MySQL).

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from db import RecallRecord, RecallSource, User, UserSession, get_db

router = APIRouter(prefix="/api/hw4")

SESSION_COOKIE_NAME = "hw4_session"
SESSION_TTL_HOURS = 24

# HW5 Part 1.I/1.II: shared format for the two new required "unique field"
# columns (recall_source.source_code, recall_record.record_code).
CODE_PATTERN = r"^[A-Za-z0-9_-]{3,40}$"


# Schemas
class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# --- HW5 Part 1.I related entity ("author"-equivalent) schemas ---
class SourceCreateIn(BaseModel):
    source_name: str = Field(..., min_length=1)
    source_region: str = Field(..., min_length=1)
    # Optional on create: auto-generated if omitted, so the HW4 UI (which
    # doesn't know about this field yet) keeps working until Part 1.III.
    source_code: Optional[str] = Field(default=None, pattern=CODE_PATTERN)


class SourceUpdateIn(BaseModel):
    source_name: str = Field(..., min_length=1)
    source_region: str = Field(..., min_length=1)
    # Optional on update: omitting it leaves the existing code unchanged
    # (PUT here behaves as "replace the fields you send", not strict REST
    # full-replacement, to stay compatible with older/partial clients).
    source_code: Optional[str] = Field(default=None, pattern=CODE_PATTERN)


class SourceOut(BaseModel):
    id: int
    source_name: str
    source_region: str
    source_code: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Primary entity schemas (HW4 Part 2, extended HW5 Part 1.I/1.II) ---
class RecordCreateIn(BaseModel):
    product_name: str = Field(..., min_length=1)
    brand_name: str = Field(..., min_length=1)
    record_code: Optional[str] = Field(default=None, pattern=CODE_PATTERN)
    units_affected: int = Field(default=0, ge=0)
    source_id: Optional[int] = None


class RecordUpdateIn(BaseModel):
    product_name: str = Field(..., min_length=1)
    brand_name: str = Field(..., min_length=1)
    record_code: Optional[str] = Field(default=None, pattern=CODE_PATTERN)
    units_affected: Optional[int] = Field(default=None, ge=0)
    source_id: Optional[int] = None


class RecordOut(BaseModel):
    id: int
    product_name: str
    brand_name: str
    record_code: str
    units_affected: int
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    source_region: Optional[str] = None
    source_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _to_record_out(rec: RecallRecord) -> RecordOut:
    return RecordOut(
        id=rec.id,
        product_name=rec.product_name,
        brand_name=rec.brand_name,
        record_code=rec.record_code,
        units_affected=rec.units_affected,
        source_id=rec.source_id,
        source_name=rec.source.source_name if rec.source else None,
        source_region=rec.source.source_region if rec.source else None,
        source_code=rec.source.source_code if rec.source else None,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _generate_code(prefix: str) -> str:
    """Short, URL-safe, collision-resistant code used when a client omits
    the required unique field on create (8 hex chars = 32 bits of entropy)."""
    return f"{prefix}-{secrets.token_hex(4).upper()}"


def _commit_or_409(db: Session, conflict_detail: str) -> None:
    """Wrap a commit that might violate a UNIQUE constraint (source_code /
    record_code) and turn the raw IntegrityError into a clean 409 instead of
    letting a 500 surface to the client."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail)


def _validate_source_id(db: Session, source_id: Optional[int]) -> None:
    """Give a clean 422 for a bad source_id instead of letting the foreign
    key constraint fail inside _commit_or_409 and get misreported as a
    source_code/record_code conflict."""
    if source_id is not None and db.get(RecallSource, source_id) is None:
        raise HTTPException(status_code=422, detail=f"source_id {source_id} does not exist")


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


# --- HW5 Part 1.II: CRUD for the related entity (recall_source) ---
@router.post("/sources", response_model=SourceOut, status_code=201)
def create_source(payload: SourceCreateIn, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    code = payload.source_code or _generate_code("SRC")
    src = RecallSource(
        source_name=payload.source_name.strip(),
        source_region=payload.source_region.strip(),
        source_code=code,
    )
    db.add(src)
    _commit_or_409(db, f"source_code '{code}' is already in use")
    db.refresh(src)
    return src


@router.get("/sources", response_model=List[SourceOut])
def list_sources(
    limit: Optional[int] = Query(default=None, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_user),
):
    q = db.query(RecallSource).order_by(RecallSource.id).offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return q.all()


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(source_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    src = db.get(RecallSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    return src


@router.put("/sources/{source_id}", response_model=SourceOut)
def update_source(
    source_id: int,
    payload: SourceUpdateIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_user),
):
    src = db.get(RecallSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    src.source_name = payload.source_name.strip()
    src.source_region = payload.source_region.strip()
    if payload.source_code is not None:
        src.source_code = payload.source_code
    _commit_or_409(db, f"source_code '{src.source_code}' is already in use")
    db.refresh(src)
    return src


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    src = db.get(RecallSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    # HW5 Part 1.I requirement: prevent deletion of a related-entity record
    # that still has associated primary-entity records (no cascade behavior
    # implemented/documented here -- this is a hard block, by design).
    dependent_count = db.query(RecallRecord).filter(RecallRecord.source_id == source_id).count()
    if dependent_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete source {source_id}: {dependent_count} recall_record "
                f"row(s) still reference it"
            ),
        )
    db.delete(src)
    db.commit()
    return {"message": f"Source {source_id} deleted"}


# HW5 Part 1.II required relationship query: all primary-entity records for
# one specific related-entity record.
@router.get("/sources/{source_id}/records", response_model=List[RecordOut])
def list_records_for_source(
    source_id: int,
    limit: Optional[int] = Query(default=None, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_user),
):
    src = db.get(RecallSource, source_id)
    if not src:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    q = (
        db.query(RecallRecord)
        .filter(RecallRecord.source_id == source_id)
        .options(joinedload(RecallRecord.source))
        .order_by(RecallRecord.id)
        .offset(offset)
    )
    if limit is not None:
        q = q.limit(limit)
    records = q.all()
    return [_to_record_out(r) for r in records]


# CRUD for the primary domain entity (recall_record), gated on login
@router.post("/records", response_model=RecordOut, status_code=201)
def create_record(payload: RecordCreateIn, db: Session = Depends(get_db), _user: User = Depends(require_user)):
    _validate_source_id(db, payload.source_id)
    code = payload.record_code or _generate_code("REC")
    rec = RecallRecord(
        product_name=payload.product_name.strip(),
        brand_name=payload.brand_name.strip(),
        record_code=code,
        units_affected=payload.units_affected,
        source_id=payload.source_id,
    )
    db.add(rec)
    _commit_or_409(db, f"record_code '{code}' is already in use")
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
def update_record(
    record_id: int,
    payload: RecordUpdateIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_user),
):
    rec = db.get(RecallRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")

    _validate_source_id(db, payload.source_id)

    rec.product_name = payload.product_name.strip()
    rec.brand_name = payload.brand_name.strip()
    if payload.record_code is not None:
        rec.record_code = payload.record_code
    if payload.units_affected is not None:
        rec.units_affected = payload.units_affected
    if payload.source_id is not None:
        rec.source_id = payload.source_id

    _commit_or_409(db, f"record_code '{rec.record_code}' is already in use")
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
