"""HW7 Part 1 screenshot demo: JWT login, /auth/me, and role-based access,
run against the live server (docker compose up, then migrate + seed users).

One section per required screenshot, so each can be captured on its own:

    python scripts/demo_auth_hw07.py login          # token on success + 401 on bad login
    python scripts/demo_auth_hw07.py me-no-token    # GET /auth/me without a token -> 401
    python scripts/demo_auth_hw07.py me-bad-token   # tampered and expired token -> 401
    python scripts/demo_auth_hw07.py create         # reader -> 403, writer/moderator -> 201
    python scripts/demo_auth_hw07.py delete         # writer -> 403, moderator -> 200
    python scripts/demo_auth_hw07.py list           # valid token -> 200
    python scripts/demo_auth_hw07.py all

Env: BASE_URL (default http://localhost:8619), HW7_*_PW (see seed_users_hw07.py),
JWT_SECRET (only used to mint the deliberately expired token).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8619")
BANNER = "Sharan Lourduraj | SID4 9619 | DATA 260 HW7"
USERS = {
    "reader1": os.environ.get("HW7_READER_PW", "Reader#9619"),
    "writer1": os.environ.get("HW7_WRITER_PW", "Writer#9619"),
    "moderator1": os.environ.get("HW7_MODERATOR_PW", "Moderator#9619"),
}
_tokens: dict[str, str] = {}


def show(label: str, resp: requests.Response) -> None:
    body = resp.text.strip()
    try:
        data = resp.json()
        if isinstance(data, dict) and "access_token" in data:
            tok = data["access_token"]
            data = {**data, "access_token": f"{tok[:48]}...({len(tok)} chars)"}
        body = str(data)
    except ValueError:
        pass
    if len(body) > 200:
        body = body[:200] + "..."
    print(f"  {label:<52} -> {resp.status_code} {resp.reason}")
    print(f"      {body}")


def call(method: str, path: str, label: str, token: str | None = None, **kw) -> requests.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.request(method, BASE_URL + path, headers=headers, timeout=15, **kw)
    show(label, resp)
    return resp


def token_for(username: str) -> str:
    if username not in _tokens:
        r = requests.post(f"{BASE_URL}/auth/login",
                          json={"username": username, "password": USERS[username]}, timeout=15)
        if r.status_code != 200:
            sys.exit(f"login as {username} failed ({r.status_code}); run migrate_hw07.py and seed_users_hw07.py first")
        _tokens[username] = r.json()["access_token"]
    return _tokens[username]


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def do_login() -> None:
    section("POST /auth/login")
    call("POST", "/auth/login", "valid credentials (writer1)", json={"username": "writer1", "password": USERS["writer1"]})
    call("POST", "/auth/login", "wrong password (writer1)", json={"username": "writer1", "password": "not-the-password"})
    call("POST", "/auth/login", "unknown user (nobody)", json={"username": "nobody", "password": "whatever"})


def do_me_no_token() -> None:
    section("GET /auth/me")
    call("GET", "/auth/me", "no Authorization header")
    call("GET", "/auth/me", "valid token (for comparison), as writer1", token=token_for("writer1"))


def do_me_bad_token() -> None:
    import jwt_auth  # local import: only this section needs the secret

    section("GET /auth/me with a bad token")
    good = token_for("writer1")
    tampered = good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB")
    call("GET", "/auth/me", "tampered token (signature changed)", token=tampered)
    me = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {good}"}, timeout=15).json()
    fake_user = SimpleNamespace(id=me["id"], username=me["username"], role=me["role"])
    expired = jwt_auth.create_access_token(fake_user, expires_delta=timedelta(minutes=-5))
    call("GET", "/auth/me", "expired token (expired 5 minutes ago)", token=expired)


def do_create() -> list[int]:
    section("POST /api/hw4/sources  (create: writer or moderator only)")
    body = {"source_name": "HW7 Demo Lab", "source_region": "Pacific Southwest"}
    call("POST", "/api/hw4/sources", "as reader1 (reader)", token_for("reader1"), json=body)
    ids = []
    for who, role in (("writer1", "writer"), ("moderator1", "moderator")):
        r = call("POST", "/api/hw4/sources", f"as {who} ({role})", token_for(who), json=body)
        if r.status_code == 201:
            ids.append(r.json()["id"])
    for sid in ids:  # tidy up so reruns do not pile up demo rows
        requests.delete(f"{BASE_URL}/api/hw4/sources/{sid}",
                        headers={"Authorization": f"Bearer {token_for('moderator1')}"}, timeout=15)
    print(f"  (cleanup) removed the {len(ids)} demo source(s) created above")
    return ids


def do_delete() -> None:
    section("DELETE /api/hw4/sources/{id}  (delete: moderator only)")
    r = requests.post(f"{BASE_URL}/api/hw4/sources", headers={"Authorization": f"Bearer {token_for('moderator1')}"},
                      json={"source_name": "HW7 Delete Demo", "source_region": "Pacific Southwest"}, timeout=15)
    sid = r.json()["id"]
    print(f"  (setup) created source id={sid} as moderator1")
    call("DELETE", f"/api/hw4/sources/{sid}", "as writer1 (writer)", token_for("writer1"))
    call("DELETE", f"/api/hw4/sources/{sid}", "as moderator1 (moderator)", token_for("moderator1"))


def do_list() -> None:
    section("GET /api/hw4/sources?limit=3  (list: any authenticated role)")
    for who, role in (("reader1", "reader"), ("writer1", "writer"), ("moderator1", "moderator")):
        resp = requests.get(f"{BASE_URL}/api/hw4/sources?limit=3",
                            headers={"Authorization": f"Bearer {token_for(who)}"}, timeout=15)
        n = len(resp.json()) if resp.status_code == 200 else "-"
        print(f"  {'as ' + who + ' (' + role + ')':<52} -> {resp.status_code} {resp.reason}   rows returned: {n}")
    call("GET", "/api/hw4/sources?limit=3", "without a token", None)


SECTIONS = {"login": do_login, "me-no-token": do_me_no_token, "me-bad-token": do_me_bad_token,
            "create": do_create, "delete": do_delete, "list": do_list}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("section", choices=[*SECTIONS, "all"])
    args = ap.parse_args()
    print(BANNER)
    print(f"target: {BASE_URL}")
    try:
        for name in (SECTIONS if args.section == "all" else [args.section]):
            SECTIONS[name]()
    except requests.ConnectionError:
        sys.exit(f"cannot reach {BASE_URL} -- is the stack up? (docker compose up --build -d)")


if __name__ == "__main__":
    main()
