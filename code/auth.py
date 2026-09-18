"""HW3 Part 1: authentication routes for the Grocery Recall Notice app.

Implements login/logout, session-backed auth, a protected dashboard, and an
idle session timeout — layered on top of the existing FastAPI app from HW1/HW2.
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

# Idle timeout: how long a session can go without activity before it's treated
# as expired, independent of the cookie's absolute max_age. Kept short (2 minutes)
# so it's practical to demo/screenshot; raise this for a real deployment.
IDLE_TIMEOUT_SECONDS = 120

# Demo credential store for the domain app. In a real system this would be a
# hashed-password lookup against a database, not a plaintext dict.
USERS = {
    "inspector": "recall2026",
}


def _get_valid_session_user(request: Request) -> str | None:
    """Returns the logged-in username if the session exists and hasn't gone idle
    too long; otherwise clears the session and returns None."""
    user = request.session.get("user")
    last_activity = request.session.get("last_activity")

    if not user or last_activity is None:
        request.session.clear()
        return None

    if time.time() - last_activity > IDLE_TIMEOUT_SECONDS:
        request.session.clear()
        return None

    # Sliding idle timeout: touch last_activity on every check against a valid session.
    request.session["last_activity"] = time.time()
    return user


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = _get_valid_session_user(request)
    return templates.TemplateResponse(request, "home.html", {"user": user})


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if _get_valid_session_user(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if USERS.get(username) == password:
        request.session["user"] = username
        request.session["last_activity"] = time.time()
        return RedirectResponse(url="/dashboard", status_code=303)

    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid username or password."},
        status_code=401,
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = _get_valid_session_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "dashboard.html", {"user": user})


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)