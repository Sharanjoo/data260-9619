"""HW7 Part 1 offline tests: JWT login, /auth/me, and role-based access on the
domain routes. Uses an in-memory SQLite database and FastAPI's TestClient, so
it needs no MySQL, Docker or network. It never touches the real database.

Usage:  python scripts/test_jwt_auth_hw07.py      (exit code 0 = all passed)
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import jwt  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import jwt_auth  # noqa: E402
from db import Base, User, get_db  # noqa: E402
from db_routes import router as db_router  # noqa: E402
from jwt_auth import create_access_token, hash_password  # noqa: E402
from jwt_auth import router as auth_router  # noqa: E402

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()
app.include_router(auth_router)
app.include_router(db_router)
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)

PASSWORDS = {"reader1": "Reader#9619", "writer1": "Writer#9619", "moderator1": "Moderator#9619"}
ROLES = {"reader1": "reader", "writer1": "writer", "moderator1": "moderator"}
with TestSession() as s:
    for name, pw in PASSWORDS.items():
        s.add(User(username=name, role=ROLES[name], password_hash=hash_password(pw)))
    s.commit()

results: list[tuple[str, bool]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))


def login(username: str) -> str:
    r = client.post("/auth/login", json={"username": username, "password": PASSWORDS[username]})
    return r.json()["access_token"]


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


tokens = {u: login(u) for u in PASSWORDS}

# --- authentication ---------------------------------------------------------
r = client.post("/auth/login", json={"username": "writer1", "password": PASSWORDS["writer1"]})
check("login valid -> 200 + bearer token", r.status_code == 200 and r.json().get("token_type") == "bearer"
      and r.json().get("access_token", "").count(".") == 2, str(r.status_code))
r = client.post("/auth/login", json={"username": "writer1", "password": "wrong"})
check("login wrong password -> 401", r.status_code == 401, str(r.status_code))
bad_pw_msg = r.json().get("detail")
r = client.post("/auth/login", json={"username": "nobody", "password": "whatever"})
check("login unknown user -> 401 with the same message", r.status_code == 401
      and r.json().get("detail") == bad_pw_msg, str(r.status_code))
r = client.post("/auth/login", json={"username": "writer1"})
check("login missing password -> 422", r.status_code == 422, str(r.status_code))

with TestSession() as s:
    hashes = [u.password_hash for u in s.query(User).all()]
check("passwords stored only as bcrypt hashes", all(h.startswith("$2") for h in hashes)
      and not any(pw in h for h in hashes for pw in PASSWORDS.values()))

# --- /auth/me ---------------------------------------------------------------
r = client.get("/auth/me")
check("GET /auth/me without token -> 401", r.status_code == 401, str(r.status_code))
r = client.get("/auth/me", headers=hdr("not.a.jwt"))
check("GET /auth/me with garbage token -> 401", r.status_code == 401, str(r.status_code))
tampered = tokens["reader1"][:-4] + ("AAAA" if not tokens["reader1"].endswith("AAAA") else "BBBB")
r = client.get("/auth/me", headers=hdr(tampered))
check("GET /auth/me with tampered signature -> 401", r.status_code == 401, str(r.status_code))
with TestSession() as s:
    writer = s.query(User).filter_by(username="writer1").one()
    expired = create_access_token(writer, expires_delta=timedelta(minutes=-5))
r = client.get("/auth/me", headers=hdr(expired))
check("GET /auth/me with expired token -> 401 'expired'", r.status_code == 401
      and "expired" in r.json().get("detail", "").lower(), f"{r.status_code} {r.text}")
forged = jwt.encode({"sub": "moderator1", "uid": 3, "role": "moderator", "iat": 1, "exp": 4102444800},
                    "some-other-secret-that-is-long-enough-0123456789", algorithm="HS256")
r = client.get("/auth/me", headers=hdr(forged))
check("token signed with a different secret -> 401", r.status_code == 401, str(r.status_code))
none_alg = jwt.encode({"sub": "moderator1", "uid": 3, "iat": 1, "exp": 4102444800}, None, algorithm="none")
r = client.get("/auth/me", headers=hdr(none_alg))
check("unsigned (alg=none) token -> 401", r.status_code == 401, str(r.status_code))
r = client.get("/auth/me", headers={"Authorization": f"Basic {tokens['reader1']}"})
check("wrong auth scheme -> 401", r.status_code == 401, str(r.status_code))
r = client.get("/auth/me", headers=hdr(tokens["moderator1"]))
check("GET /auth/me valid token -> identity + role", r.status_code == 200
      and r.json().get("username") == "moderator1" and r.json().get("role") == "moderator", r.text)

# --- list / read: any authenticated role -------------------------------------
for u in PASSWORDS:
    r = client.get("/api/hw4/sources", headers=hdr(tokens[u]))
    check(f"list sources as {ROLES[u]} -> 200", r.status_code == 200, str(r.status_code))
r = client.get("/api/hw4/sources")
check("list sources without token -> 401", r.status_code == 401, str(r.status_code))
r = client.get("/api/hw4/records", headers=hdr(tokens["reader1"]))
check("list records as reader -> 200", r.status_code == 200, str(r.status_code))

# --- create: writer or moderator ----------------------------------------------
body = {"source_name": "State Lab", "source_region": "West"}
r = client.post("/api/hw4/sources", json=body, headers=hdr(tokens["reader1"]))
check("create source as reader -> 403", r.status_code == 403, str(r.status_code))
r = client.post("/api/hw4/sources", json=body)
check("create source without token -> 401", r.status_code == 401, str(r.status_code))
r = client.post("/api/hw4/sources", json=body, headers=hdr(tokens["writer1"]))
check("create source as writer -> 201", r.status_code == 201, str(r.status_code))
writer_source = r.json().get("id")
r = client.post("/api/hw4/sources", json=body, headers=hdr(tokens["moderator1"]))
check("create source as moderator -> 201", r.status_code == 201, str(r.status_code))
mod_source = r.json().get("id")
rec = {"product_name": "Peanut Butter", "brand_name": "GreenAcre", "units_affected": 12}
r = client.post("/api/hw4/records", json=rec, headers=hdr(tokens["reader1"]))
check("create record as reader -> 403", r.status_code == 403, str(r.status_code))
r = client.post("/api/hw4/records", json=rec, headers=hdr(tokens["writer1"]))
check("create record as writer -> 201", r.status_code == 201, str(r.status_code))
record_id = r.json().get("id")
r = client.post("/api/hw4/records", json={"product_name": ""}, headers=hdr(tokens["writer1"]))
check("create record invalid body as writer -> 422", r.status_code == 422, str(r.status_code))

# --- update: writer or moderator (a write) -------------------------------------
upd = {"product_name": "Peanut Butter (recalled)", "brand_name": "GreenAcre"}
r = client.put(f"/api/hw4/records/{record_id}", json=upd, headers=hdr(tokens["reader1"]))
check("update record as reader -> 403", r.status_code == 403, str(r.status_code))
r = client.put(f"/api/hw4/records/{record_id}", json=upd, headers=hdr(tokens["writer1"]))
check("update record as writer -> 200", r.status_code == 200, str(r.status_code))

# --- delete: moderator only ------------------------------------------------------
r = client.delete(f"/api/hw4/records/{record_id}", headers=hdr(tokens["writer1"]))
check("delete record as writer -> 403", r.status_code == 403, str(r.status_code))
r = client.delete(f"/api/hw4/records/{record_id}", headers=hdr(tokens["reader1"]))
check("delete record as reader -> 403", r.status_code == 403, str(r.status_code))
r = client.delete(f"/api/hw4/records/{record_id}")
check("delete record without token -> 401", r.status_code == 401, str(r.status_code))
r = client.delete(f"/api/hw4/records/{record_id}", headers=hdr(tokens["moderator1"]))
check("delete record as moderator -> 200", r.status_code == 200, str(r.status_code))
r = client.delete(f"/api/hw4/records/{record_id}", headers=hdr(tokens["moderator1"]))
check("delete missing record as moderator -> 404", r.status_code == 404, str(r.status_code))
r = client.delete(f"/api/hw4/sources/{writer_source}", headers=hdr(tokens["writer1"]))
check("delete source as writer -> 403", r.status_code == 403, str(r.status_code))
r = client.delete(f"/api/hw4/sources/{mod_source}", headers=hdr(tokens["moderator1"]))
check("delete source as moderator -> 200", r.status_code == 200, str(r.status_code))

# --- the token follows the database, not just its own claims ------------------------
with TestSession() as s:
    s.query(User).filter_by(username="writer1").one().role = "reader"
    s.commit()
r = client.post("/api/hw4/sources", json=body, headers=hdr(tokens["writer1"]))
check("role demoted in DB -> old writer token now gets 403", r.status_code == 403, str(r.status_code))
with TestSession() as s:
    s.query(User).filter_by(username="writer1").delete()
    s.commit()
r = client.get("/auth/me", headers=hdr(tokens["writer1"]))
check("user deleted from DB -> old token gets 401", r.status_code == 401, str(r.status_code))

# --- the HW4 session scheme is gone from the HW7 routes ------------------------------
r = client.post("/api/hw4/auth/login", json={"email": "a@b.co", "password": "x"})
check("HW4 session login route no longer exists -> 404", r.status_code == 404, str(r.status_code))
check("jwt secret is long enough for HS256", len(jwt_auth.JWT_SECRET) >= 32)

passed = sum(1 for _, ok in results if ok)
print(f"\n{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
