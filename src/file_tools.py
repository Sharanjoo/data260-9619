"""HW7 Part 6: the six file tools (read_file, write_file, edit_file, glob_files,
search_in_files, bash), confined to one sandbox directory.

Every tool returns the same envelope the HW5 domain tools use, so it can be plugged into
execute_tool(..., tools=FileTools(root).registry()) and the agent loop unchanged:

    {"ok": bool, "data": {...} | None, "error": str | None}

and never raises. The file tools cannot leave ``root``: absolute paths outside it, ``..``
escapes and symlinks that point outside are all refused. ``bash`` goes through the safety
gate in safety_gate.py before anything runs; the model cannot confirm a destructive
command (the tool schema has no such argument): only the harness constructing FileTools
can set ``auto_approve``, and ``confirmed`` is never exposed.
"""
from __future__ import annotations

import difflib
import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .safety_gate import confirm_bash

MAX_FILE_BYTES = 1_000_000
MAX_OUTPUT_CHARS = 8000
MAX_DIFF_LINES = 40
BASH_TIMEOUT_S = 10


def _ok(**data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}


def _err(message: str, **data: Any) -> dict:
    return {"ok": False, "data": data or None, "error": message}


class SandboxError(ValueError):
    pass


class FileTools:
    def __init__(self, root: str | Path, auto_approve: bool = False) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise SandboxError(f"sandbox directory does not exist: {self.root}")
        self.auto_approve = auto_approve  # harness-level setting, never a model argument

    # --- path handling --------------------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise SandboxError("path must be a non-empty string")
        if "\x00" in path:
            raise SandboxError("path contains a null byte")
        resolved = (self.root / path).resolve()  # an absolute `path` replaces self.root here
        if resolved != self.root and self.root not in resolved.parents:
            raise SandboxError(f"path {path!r} is outside the sandbox")
        return resolved

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def _inside(self, p: Path) -> bool:
        try:
            r = p.resolve()
        except (OSError, RuntimeError):
            return False
        return r == self.root or self.root in r.parents

    # --- tools ------------------------------------------------------------------------------

    def read_file(self, path: str, max_lines: Optional[int] = None) -> dict:
        try:
            p = self._resolve(path)
            if not p.is_file():
                return _err(f"not a file: {path}")
            if p.stat().st_size > MAX_FILE_BYTES:
                return _err(f"file too large to read ({p.stat().st_size} bytes; limit {MAX_FILE_BYTES})")
            if max_lines is not None and (not isinstance(max_lines, int) or isinstance(max_lines, bool) or max_lines < 1):
                return _err("max_lines must be a positive integer")
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            shown = lines if max_lines is None else lines[:max_lines]
            return _ok(path=self._rel(p), content="\n".join(shown), lines_returned=len(shown),
                       total_lines=len(lines), truncated=len(shown) < len(lines))
        except (ValueError, OSError) as exc:
            return _err(str(exc))

    def write_file(self, path: str, content: str) -> dict:
        try:
            p = self._resolve(path)
            if p == self.root or p.is_dir():
                return _err(f"cannot write to a directory: {path}")
            if not isinstance(content, str):
                return _err("content must be a string")
            if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                return _err(f"content too large (limit {MAX_FILE_BYTES} bytes)")
            existed = p.exists()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8", newline="\n")
            return _ok(path=self._rel(p), bytes_written=len(content.encode("utf-8")), created=not existed)
        except (ValueError, OSError) as exc:
            return _err(str(exc))

    def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> dict:
        """Replace old_text with new_text. old_text must occur exactly once unless replace_all."""
        try:
            p = self._resolve(path)
            if not p.is_file():
                return _err(f"not a file: {path}")
            if not isinstance(old_text, str) or not old_text:
                return _err("old_text must be a non-empty string")
            if not isinstance(new_text, str):
                return _err("new_text must be a string")
            before = p.read_text(encoding="utf-8", errors="replace")
            count = before.count(old_text)
            if count == 0:
                return _err("old_text not found in the file")
            if count > 1 and not replace_all:
                return _err(f"old_text appears {count} times; make it unique or set replace_all")
            after = before.replace(old_text, new_text) if replace_all else before.replace(old_text, new_text, 1)
            p.write_text(after, encoding="utf-8", newline="\n")
            rel = self._rel(p)
            diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                             f"a/{rel}", f"b/{rel}", lineterm="", n=1))
            clipped = len(diff) > MAX_DIFF_LINES
            return _ok(path=rel, replacements=count if replace_all else 1,
                       diff="\n".join(diff[:MAX_DIFF_LINES]) + ("\n... (diff truncated)" if clipped else ""))
        except (ValueError, OSError) as exc:
            return _err(str(exc))

    def glob_files(self, pattern: str, max_results: int = 100) -> dict:
        try:
            if not isinstance(pattern, str) or not pattern.strip():
                return _err("pattern must be a non-empty string")
            if pattern.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", pattern) or ".." in re.split(r"[\\/]", pattern):
                return _err("pattern must be relative to the sandbox and contain no '..'")
            if not isinstance(max_results, int) or isinstance(max_results, bool) or max_results < 1:
                return _err("max_results must be a positive integer")
            found = sorted(self._rel(m) for m in self.root.glob(pattern) if m.is_file() and self._inside(m))
            return _ok(pattern=pattern, matches=found[:max_results], count=len(found), truncated=len(found) > max_results)
        except (OSError, ValueError) as exc:
            return _err(str(exc))

    def search_in_files(self, pattern: str, file_pattern: str = "*", max_results: int = 50,
                        use_regex: bool = False, ignore_case: bool = False) -> dict:
        """Find lines containing `pattern` (literal text, or a regex with use_regex) in the
        files whose name or relative path matches the glob `file_pattern`."""
        try:
            if not isinstance(pattern, str) or not pattern:
                return _err("pattern must be a non-empty string")
            if not isinstance(file_pattern, str) or not file_pattern:
                return _err("file_pattern must be a non-empty string")
            if not isinstance(max_results, int) or isinstance(max_results, bool) or max_results < 1:
                return _err("max_results must be a positive integer")
            flags = re.IGNORECASE if ignore_case else 0
            try:
                rx = re.compile(pattern if use_regex else re.escape(pattern), flags)
            except re.error as exc:
                return _err(f"invalid regex: {exc}")
            matches: List[dict] = []
            files_scanned = 0
            total = 0
            for f in sorted(self.root.rglob("*")):
                if not f.is_file() or not self._inside(f):
                    continue
                rel = self._rel(f)
                if not (fnmatch.fnmatch(f.name, file_pattern) or fnmatch.fnmatch(rel, file_pattern)):
                    continue
                try:
                    if f.stat().st_size > MAX_FILE_BYTES:
                        continue
                    text = f.read_bytes()
                except OSError:
                    continue
                if b"\x00" in text[:2048]:  # binary
                    continue
                files_scanned += 1
                for n, line in enumerate(text.decode("utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        total += 1
                        if len(matches) < max_results:
                            matches.append({"file": rel, "line": n, "text": line.strip()[:200]})
            return _ok(pattern=pattern, file_pattern=file_pattern, matches=matches, match_count=total,
                       files_scanned=files_scanned, truncated=total > len(matches))
        except OSError as exc:
            return _err(str(exc))

    def bash(self, command: str) -> dict:
        """Run a shell command in the sandbox, but only if the safety gate allows it."""
        gate = confirm_bash(command, auto_approve=self.auto_approve)
        if not gate["allowed"]:
            return _err(f"blocked by safety gate: {gate['reason']}", gate=gate, command=command, executed=False)
        try:
            done = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True,
                                  timeout=BASH_TIMEOUT_S, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return _err(f"command timed out after {BASH_TIMEOUT_S}s", gate=gate, command=command, executed=True)
        except OSError as exc:
            return _err(str(exc), gate=gate, command=command, executed=False)
        return _ok(command=command, exit_code=done.returncode, stdout=done.stdout[:MAX_OUTPUT_CHARS],
                   stderr=done.stderr[:MAX_OUTPUT_CHARS], gate=gate, executed=True)

    # --- integration with the agent loop -----------------------------------------------------

    def registry(self) -> Dict[str, Callable[..., dict]]:
        """{tool name: callable}, the shape execute_tool(..., tools=...) expects."""
        return {name: getattr(self, name) for name in TOOL_NAMES}


TOOL_NAMES = ("read_file", "write_file", "edit_file", "glob_files", "search_in_files", "bash")

# JSON schemas for the model. `bash` exposes only `command`: the model cannot pass
# auto_approve or a confirmation flag, so it cannot unlock a destructive command.
TOOL_SCHEMAS: List[dict] = [
    {"name": "read_file", "description": "Read a text file in the sandbox. Use max_lines to read only the start.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "path relative to the sandbox"},
         "max_lines": {"type": "integer", "minimum": 1}}, "required": ["path"]}},
    {"name": "write_file", "description": "Create or overwrite a text file in the sandbox.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace old_text with new_text in a file and return a short diff.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"},
         "replace_all": {"type": "boolean"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob_files", "description": "List files in the sandbox matching a glob such as '**/*.py'.",
     "parameters": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1}}, "required": ["pattern"]}},
    {"name": "search_in_files", "description": "Find lines containing text (or a regex) in files matching file_pattern.",
     "parameters": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "file_pattern": {"type": "string", "description": "glob, default '*'"},
         "max_results": {"type": "integer", "minimum": 1}, "use_regex": {"type": "boolean"},
         "ignore_case": {"type": "boolean"}}, "required": ["pattern"]}},
    {"name": "bash", "description": "Run a shell command in the sandbox. Read-only commands run; anything risky is blocked.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
]
