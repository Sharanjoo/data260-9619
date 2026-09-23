"""HW4 Part 2: MySQL persistence via SQLAlchemy.

Database: s9619_rel (PREFIX=s9619 + "_rel", per Section 0).
Required exact variable name for the DB connection/session factory: db_session_basede26.
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


# --- Required exact variable name (HW4 Part 2 spec): 'db_session_basede26' ---
db_session_basede26 = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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
    """Part 3's '200 related rows': the reporting/inspection source for a recall.

    Just test data for now per the spec ("you'll build a proper related
    entity with full CRUD in a later homework") — read-only here.
    """

    __tablename__ = "recall_source"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(150), nullable=False)
    source_region = Column(String(100), nullable=False)


class RecallRecord(Base):
    """Part 2's required 3-column primary entity table.

    product_name = primary field, brand_name = secondary field.
    source_id is the Part-3 FK to the 200 related rows (nullable so Part 2
    works standalone before Part 3's seed script runs).
    """

    __tablename__ = "recall_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String(200), nullable=False)
    brand_name = Column(String(150), nullable=False)
    source_id = Column(Integer, ForeignKey("recall_source.id"), nullable=True)

    source = relationship("RecallSource")


def init_db() -> None:
    """Idempotent schema bootstrap; the literal migration also lives in
    scripts/schema_hw04.sql for the Part 3 'commit your schema/migration' requirement."""
    Base.metadata.create_all(bind=engine)


def get_db():
    db: Session = db_session_basede26()
    try:
        yield db
    finally:
        db.close()
