"""HW7 Part 1: JWT bearer authentication and role-based access control.

Replaces HW4's server-side-session login on the graded domain routes.
Passwords are stored only as bcrypt hashes in the MySQL ``users`` table.
A token is issued only after the password has been verified against that
hash, and every protected request re-loads the user from the database, so
a deleted user or a changed role takes effect immediately instead of
waiting for the token to expire.

Roles: reader < writer < moderator (see the *_ROLES tuples below).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import User, get_db

# The fallback secret is for local homework demos only; set JWT_SECRET in a
# real deployment. HS256 needs at least 32 bytes of secret.
JWT_SECRET = os.environ.get("JWT_SECRET", "hw7-dev-secret-s9619-change-me-0123456789")
JWT_ALGORITHM = "HS256"
JWT_TTL_MINUTES = int(os.environ.get("JWT_TTL_MINUTES", "30"))

ROLES = ("reader", "writer", "moderator")
READ_ROLES = ROLES  # list / read: any authenticated role
WRITE_ROLES = ("writer", "moderator")  # create / update
DELETE_ROLES = ("moderator",)  # delete

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)  # we raise our own 401 so the body is consistent

# A real bcrypt hash that no password matches. Login verifies against it when
# the username does not exist, so "unknown user" and "wrong password" cost the
# same time and cannot be told apart by timing.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode("utf-8")


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:  # malformed hash, or password longer than bcrypt's 72 bytes
        return False


def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    ttl = expires_delta if expires_delta is not None else timedelta(minutes=JWT_TTL_MINUTES)
    claims = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,  # informational; authorization re-reads the role from MySQL
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """401 for a missing, malformed, tampered or expired token (or a user that
    no longer exists). Returns the authenticated User otherwise."""
    if creds is None or not creds.credentials:
        raise _unauthorized("Not authenticated: missing bearer token")
    try:
        # algorithms is pinned, so an "alg: none" or other-algorithm token is rejected.
        claims = jwt.decode(
            creds.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "uid"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token has expired") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token") from None

    uid = claims.get("uid")
    user = db.get(User, uid) if isinstance(uid, int) else None
    if user is None or user.username != claims.get("sub"):
        raise _unauthorized("Invalid token: user no longer exists")
    return user


def require_roles(*allowed: str):
    """Dependency factory: 403 when the authenticated user's role is not allowed."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Forbidden: role '{user.role}' may not do this "
                    f"(requires one of: {', '.join(allowed)})"
                ),
            )
        return user

    return _dep


# Ready-made dependencies for the domain routes.
require_reader = require_roles(*READ_ROLES)
require_writer = require_roles(*WRITE_ROLES)
require_moderator = require_roles(*DELETE_ROLES)


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    stored_hash = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = verify_password(payload.password, stored_hash)
    if user is None or not password_ok:
        # Same message for "no such user" and "wrong password".
        raise _unauthorized("Invalid username or password")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "expires_in": JWT_TTL_MINUTES * 60,
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}
