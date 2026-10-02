"""HW4 Part 2: MySQL persistence via SQLAlchemy.

Database: s9619_rel (PREFIX=s9619 + "_rel", per Section 0).
Required exact variable name for the DB connection/session factory: SessionLocal.
"""
from __future__ import annotations

import os

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine, func
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = os.environ.get("MYSQL_PORT", "3306")
MYSQL_USER = os.environ.get("MYSQL_USER", "hw4_user")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "hw4_pass_9619")
MYSQL_DB = os.environ.get("MYSQL_DB", "s9619_rel")

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)

# --- Part 3: per-request SQL statement counter (thread-local via contextvars,
# correctly propagated into FastAPI's sync-endpoint threadpool by anyio) ---
import contextvars
from sqlalchemy import event

_query_count_var: contextvars.ContextVar[list] = contextvars.ContextVar("query_count", default=None)


def reset_query_counter() -> None:
    _query_count_var.set([0])


def get_query_count() -> int:
    box = _query_count_var.get()
    return box[0] if box else 0


@event.listens_for(engine, "before_cursor_execute")
def _count_query(conn, cursor, statement, parameters, context, executemany):
    box = _query_count_var.get()
    if box is not None:
        box[0] += 1


# --- Required exact variable name (HW4 Part 2 spec): 'SessionLocal' ---
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


class User(Base):
    """HW4 Part 2 required table: users(id, name, email UNIQUE, password_hash)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    email = Column(String(190), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)


class UserSession(Base):
    """HW4 Part 2 required table: sessions(id [token], user_id, created_at, expires_at).

    id is the opaque session token itself — the only thing the browser's
    HttpOnly cookie ever holds. No user data lives in the cookie.
    """

    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User")


class RecallSource(Base):
    """HW5 Part 1.I required related entity: the reporting/inspection source
    for a recall (the "author"-equivalent side of the relationship).

    source_name = primary text field, source_region = secondary text field,
    source_code = required unique field, created_at/updated_at = timestamps.
    Full CRUD lives in db_routes.py as of HW5 (read-only in HW4).
    """

    __tablename__ = "recall_source"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(150), nullable=False)
    source_region = Column(String(100), nullable=False)
    source_code = Column(String(40), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    records = relationship("RecallRecord", back_populates="source")


class RecallRecord(Base):
    """HW5 Part 1.I required primary entity table.

    product_name = primary field, brand_name = secondary field,
    record_code = required unique field, units_affected = numeric field with
    a sensible default (0), source_id = FK to the related entity (left
    nullable -- unchanged from HW4 -- so existing rows created through the
    HW4 API, which never set it, stay valid; see scripts/migrate_hw05.py),
    plus created_at/updated_at timestamps.
    """

    __tablename__ = "recall_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String(200), nullable=False)
    brand_name = Column(String(150), nullable=False)
    record_code = Column(String(40), unique=True, nullable=False, index=True)
    units_affected = Column(Integer, nullable=False, default=0, server_default="0")
    source_id = Column(Integer, ForeignKey("recall_source.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    source = relationship("RecallSource", back_populates="records")


def init_db() -> None:
    """Idempotent schema bootstrap for brand-new tables; the literal migrations
    also live in scripts/schema_hw04.sql (Part 3) and scripts/schema_hw05.sql
    (Part 1.I) for the 'commit your schema/migration' requirement. NOTE:
    create_all() only creates tables that don't exist yet -- it does NOT add
    new columns to an already-existing table, so the HW5 recall_source /
    recall_record column additions are applied separately by
    scripts/migrate_hw05.py, not by this function."""
    Base.metadata.create_all(bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
