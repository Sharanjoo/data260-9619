"""Run: python scripts/test_doc_api_hw06.py  (needs: pip install mongomock)
Offline tests for the HW6 Part 1 API (no real MongoDB needed): uses mongomock
as a stand-in collection via FastAPI's dependency override."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

import mongomock
from fastapi.testclient import TestClient

from doc_api import routes
from doc_api.server import create_app

app = create_app()
col = mongomock.MongoClient(tz_aware=True)["s9619_doc"]["recall_notices"]
app.dependency_overrides[routes.get_collection] = lambda: col
c = TestClient(app, raise_server_exceptions=False)
URL = "/api/hw6/notices"
GOOD = {"title": "Frozen Mixed Berries", "category": "food-safety-recall", "notice_date": "2026-10-01T09:30:00Z"}
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
    print(("PASS" if cond else "FAIL"), name, detail)


# create
r = c.post(URL, json={**GOOD, "description": "  Possible contamination.  "})
check("create 201", r.status_code == 201, r.text[:120])
doc = r.json()
nid = doc["id"]
check("default status open", doc["status"] == "open")
check("description trimmed", doc["description"] == "Possible contamination.")
check("timestamps set and equal on create", doc["created_at"] == doc["updated_at"] and doc["created_at"].endswith(("Z", "+00:00")), doc["created_at"])
# create with minimal + blank description -> None
r = c.post(URL, json={**GOOD, "title": "Second", "description": "   ", "status": "investigating"})
check("blank description -> null", r.status_code == 201 and r.json()["description"] is None and r.json()["status"] == "investigating")
# list newest first
r = c.get(URL)
check("list 200 newest first", r.status_code == 200 and [d["title"] for d in r.json()] == ["Second", "Frozen Mixed Berries"], str([d["title"] for d in r.json()]))
check("list filter status", [d["title"] for d in c.get(URL, params={"status": "investigating"}).json()] == ["Second"])
check("list filter bad enum 422", c.get(URL, params={"status": "bogus"}).status_code == 422)
check("list limit 0 -> 422", c.get(URL, params={"limit": 0}).status_code == 422)
check("list limit/skip", len(c.get(URL, params={"limit": 1, "skip": 1}).json()) == 1)
# get one
r = c.get(f"{URL}/{nid}")
check("get one 200", r.status_code == 200 and r.json()["id"] == nid)
check("get unknown id 404", c.get(f"{URL}/64b7f0f0f0f0f0f0f0f0f0f0").status_code == 404)
r = c.get(f"{URL}/not-an-id")
check("get malformed id 422", r.status_code == 422 and "24-character" in r.text, r.text[:100])
# update
import time; time.sleep(0.01)
r = c.put(f"{URL}/{nid}", json={**GOOD, "title": "Frozen Berries (updated)", "status": "resolved", "notice_date": "2026-10-02"})
check("update 200", r.status_code == 200 and r.json()["title"] == "Frozen Berries (updated)" and r.json()["status"] == "resolved", r.text[:150])
check("update bumps updated_at only", r.json()["updated_at"] > r.json()["created_at"] and r.json()["created_at"] == doc["created_at"])
check("update unknown 404", c.put(f"{URL}/64b7f0f0f0f0f0f0f0f0f0f0", json=GOOD).status_code == 404)
check("update invalid body 422", c.put(f"{URL}/{nid}", json={"title": ""}).status_code == 422)
# validation matrix
def expect422(name, body, field):
    r = c.post(URL, json=body)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    ok = r.status_code == 422 and j.get("error") == "validation_failed" and any(d["field"] == field or field == "" for d in j.get("details", []))
    check(name, ok, f"{r.status_code} {r.text[:200]}")
expect422("missing title", {k: v for k, v in GOOD.items() if k != "title"}, "title")
expect422("missing category", {k: v for k, v in GOOD.items() if k != "category"}, "category")
expect422("missing notice_date", {k: v for k, v in GOOD.items() if k != "notice_date"}, "notice_date")
expect422("title 101 chars", {**GOOD, "title": "x" * 101}, "title")
expect422("title blank", {**GOOD, "title": "   "}, "title")
expect422("title wrong type", {**GOOD, "title": 123}, "title")
expect422("bad status enum", {**GOOD, "status": "closed"}, "status")
expect422("bad category enum", {**GOOD, "category": "spoilage"}, "category")
expect422("bad date", {**GOOD, "notice_date": "yesterday"}, "notice_date")
expect422("description too long", {**GOOD, "description": "d" * 1001}, "description")
expect422("unknown field", {**GOOD, "statuss": "open"}, "statuss")
r = c.post(URL, content="{bad json", headers={"content-type": "application/json"})
check("malformed JSON 422", r.status_code == 422 and r.json().get("error") == "validation_failed", r.text[:150])
check("100-char title accepted", c.post(URL, json={**GOOD, "title": "y" * 100}).status_code == 201)
# delete
r = c.delete(f"{URL}/{nid}")
check("delete 200", r.status_code == 200 and r.json() == {"deleted": True, "id": nid})
check("get after delete 404", c.get(f"{URL}/{nid}").status_code == 404)
check("delete again 404", c.delete(f"{URL}/{nid}").status_code == 404)
# other routes keep default 422 shape
other = FastAPI = None
from fastapi import FastAPI as _F
a2 = create_app()
@a2.get("/api/other/{n}")
def _o(n: int): return {"n": n}
r = TestClient(a2).get("/api/other/abc")
check("non-HW6 route keeps FastAPI default 422", r.status_code == 422 and "detail" in r.json() and "error" not in r.json(), r.text[:120])
# database failure -> 503 / 500
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure
class Boom:
    def __init__(self, exc): self.exc = exc
    def find(self, *a, **k): raise self.exc
for exc, code in [(ServerSelectionTimeoutError("down"), 503), (OperationFailure("weird", code=999), 500)]:
    app.dependency_overrides[routes.get_collection] = lambda e=exc: Boom(e)
    r = c.get(URL)
    check(f"db failure {type(exc).__name__} -> {code}", r.status_code == code, r.text[:120])
print(f"\n{passed}/{passed+failed} checks passed")
sys.exit(1 if failed else 0)
