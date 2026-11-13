"""Cached readers: @st.cache_data keyed on the file's modification time, so a page reloads a log only when it changed."""
from __future__ import annotations

from pathlib import Path
from typing import List

import streamlit as st

from dashboard import data


def _mtime(path: Path) -> float:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False)
def _spans(path: str, mtime: float) -> List[dict]:
    return data.read_jsonl(Path(path))


@st.cache_data(show_spinner=False)
def _evals(path: str, mtime: float) -> List[dict]:
    return data.read_jsonl(Path(path))


@st.cache_data(show_spinner=False)
def _csv(path: str, mtime: float) -> List[dict]:
    return data.read_csv(Path(path))


@st.cache_data(show_spinner=False)
def _json(path: str, mtime: float):
    return data.read_json(Path(path))


def spans() -> List[dict]:
    return _spans(str(data.SPANS), _mtime(data.SPANS))


def evals() -> List[dict]:
    return _evals(str(data.EVALS), _mtime(data.EVALS))


def per_case() -> List[dict]:
    return _csv(str(data.PER_CASE), _mtime(data.PER_CASE))


def validation():
    return _json(str(data.VALIDATION), _mtime(data.VALIDATION))


def examples() -> dict:
    return {"runs": _evals(str(data.LATENCY_RUNS), _mtime(data.LATENCY_RUNS)), "failed": _json(str(data.FAILED), _mtime(data.FAILED))}
