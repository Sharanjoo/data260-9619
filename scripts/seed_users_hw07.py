"""HW7 Part 1: create (or reset) the three demo users, one per role.

Passwords are stored only as bcrypt hashes. Override the demo passwords with
HW7_READER_PW / HW7_WRITER_PW / HW7_MODERATOR_PW. Idempotent: rerunning
resets each demo user's password and role.

Usage (repo root):  python scripts/seed_users_hw07.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Host-side script: use the host-mapped MySQL port from compose.yaml (43306), like verify_hw05.py.
os.environ.setdefault("MYSQL_PORT", "43306")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from db import SessionLocal, User, init_db  # noqa: E402
from jwt_auth import hash_password  # noqa: E402

DEMO_USERS = {
    "reader1": ("reader", os.environ.get("HW7_READER_PW", "Reader#9619")),
    "writer1": ("writer", os.environ.get("HW7_WRITER_PW", "Writer#9619")),
    "moderator1": ("moderator", os.environ.get("HW7_MODERATOR_PW", "Moderator#9619")),
}


def seed(session) -> None:
    for username, (role, password) in DEMO_USERS.items():
        user = session.query(User).filter(User.username == username).first()
        action = "updated"
        if user is None:
            user = User(username=username, role=role, password_hash="")
            session.add(user)
            action = "created"
        user.role = role
        user.password_hash = hash_password(password)
        print(f"[seed_users_hw07] {action}: {username:<11} role={role}")
    session.commit()


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        seed(session)
