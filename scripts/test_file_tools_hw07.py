"""HW7 Part 6: offline tests for the six file tools (src/file_tools.py).

Everything happens inside a temporary sandbox directory that is deleted afterwards. No
model, no network, no database.

Usage:  python scripts/test_file_tools_hw07.py      (exit code 0 = all passed)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.file_tools import TOOL_NAMES, TOOL_SCHEMAS, FileTools  # noqa: E402

results = []
ESCAPE_NAME = f"hw07_escape_{os.getpid()}.txt"  # unique, so a leftover can never confuse a later run


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))


with tempfile.TemporaryDirectory(prefix="hw07_sandbox_") as tmp, tempfile.TemporaryDirectory(prefix="hw07_outside_") as outside:
    root = Path(tmp)
    ft = FileTools(root)
    (Path(outside) / "secret.txt").write_text("TOP SECRET", encoding="utf-8")

    # --- write_file ---------------------------------------------------------------------------
    r = ft.write_file("notes.txt", "line1\nline2\nline3\nline4\nline5\n")
    check("write_file creates a file", r["ok"] and r["data"]["created"] and r["data"]["bytes_written"] == 30, str(r))
    r = ft.write_file("pkg/sub/deep.py", "x = 1\n")
    check("write_file creates parent directories", r["ok"] and (root / "pkg/sub/deep.py").is_file(), str(r))
    r = ft.write_file("notes.txt", "overwritten\n")
    check("write_file overwrite reports created=False", r["ok"] and r["data"]["created"] is False, str(r))
    ft.write_file("notes.txt", "line1\nline2\nline3\nline4\nline5\n")
    check("write_file to a directory path fails", not ft.write_file("pkg", "x")["ok"])
    check("write_file non-string content fails", not ft.write_file("a.txt", 5)["ok"])  # type: ignore[arg-type]
    check("write_file too large fails", not ft.write_file("big.txt", "x" * 1_000_001)["ok"])

    # --- read_file ----------------------------------------------------------------------------
    r = ft.read_file("notes.txt")
    check("read_file returns all lines", r["ok"] and r["data"]["total_lines"] == 5 and not r["data"]["truncated"], str(r))
    r = ft.read_file("notes.txt", max_lines=2)
    check("read_file max_lines truncates", r["ok"] and r["data"]["content"] == "line1\nline2"
          and r["data"]["lines_returned"] == 2 and r["data"]["truncated"] and r["data"]["total_lines"] == 5, str(r))
    check("read_file max_lines larger than file", ft.read_file("notes.txt", max_lines=99)["data"]["truncated"] is False)
    check("read_file max_lines=0 rejected", not ft.read_file("notes.txt", max_lines=0)["ok"])
    check("read_file max_lines bool rejected", not ft.read_file("notes.txt", max_lines=True)["ok"])  # type: ignore[arg-type]
    check("read_file missing file -> error envelope", ft.read_file("nope.txt")["ok"] is False)
    check("read_file on a directory fails", not ft.read_file("pkg")["ok"])
    (root / "huge.bin").write_bytes(b"a" * 1_000_001)
    check("read_file refuses a huge file", not ft.read_file("huge.bin")["ok"])

    # --- sandbox confinement ------------------------------------------------------------------
    for label, bad in (("parent-directory escape", f"../{ESCAPE_NAME}"),
                       ("nested escape", f"pkg/../../{ESCAPE_NAME}"),
                       ("absolute path outside", str(Path(outside) / "secret.txt")),
                       ("absolute system path", "/etc/passwd" if os.name != "nt" else "C:\\Windows\\win.ini")):
        check(f"read_file refuses {label}", not ft.read_file(bad)["ok"], bad)
        check(f"write_file refuses {label}", not ft.write_file(bad, "x")["ok"], bad)
    stray = root.parent / ESCAPE_NAME
    check("nothing was written outside the sandbox", not stray.exists())
    stray.unlink(missing_ok=True)  # clean up if a broken tool ever wrote it
    check("absolute path INSIDE the sandbox is accepted", ft.read_file(str(root / "notes.txt"))["ok"])
    try:
        os.symlink(Path(outside) / "secret.txt", root / "link_out.txt")
        check("read_file refuses a symlink that points outside", not ft.read_file("link_out.txt")["ok"])
        found = ft.search_in_files("SECRET")["data"]["matches"]
        check("search_in_files does not follow a symlink out of the sandbox", all(m["file"] != "link_out.txt" for m in found))
        check("glob_files does not list a symlink that points outside", "link_out.txt" not in ft.glob_files("*")["data"]["matches"])
    except (OSError, NotImplementedError):
        print("[SKIP] symlink tests (this system cannot create symlinks)")

    # --- edit_file ----------------------------------------------------------------------------
    r = ft.edit_file("notes.txt", "line3", "LINE THREE")
    check("edit_file replaces once and returns a diff", r["ok"] and r["data"]["replacements"] == 1
          and "-line3" in r["data"]["diff"] and "+LINE THREE" in r["data"]["diff"], str(r))
    check("edit_file actually changed the file", "LINE THREE" in ft.read_file("notes.txt")["data"]["content"])
    check("edit_file diff has a header", "--- a/notes.txt" in r["data"]["diff"] and "+++ b/notes.txt" in r["data"]["diff"])
    r = ft.edit_file("notes.txt", "not-there", "x")
    check("edit_file: text not found -> error", not r["ok"] and "not found" in r["error"], str(r))
    ft.write_file("dup.txt", "a\na\nb\n")
    r = ft.edit_file("dup.txt", "a", "z")
    check("edit_file: ambiguous match -> error, file unchanged", not r["ok"] and "2 times" in r["error"]
          and ft.read_file("dup.txt")["data"]["content"] == "a\na\nb", str(r))
    r = ft.edit_file("dup.txt", "a", "z", replace_all=True)
    check("edit_file replace_all replaces every occurrence", r["ok"] and r["data"]["replacements"] == 2
          and ft.read_file("dup.txt")["data"]["content"] == "z\nz\nb", str(r))
    check("edit_file empty old_text rejected", not ft.edit_file("dup.txt", "", "x")["ok"])
    check("edit_file on a missing file fails", not ft.edit_file("nope.txt", "a", "b")["ok"])
    check("edit_file refuses an escape", not ft.edit_file("../x.txt", "a", "b")["ok"])
    ft.write_file("long.txt", "".join(f"row {i}\n" for i in range(200)))
    r = ft.edit_file("long.txt", "row", "ROW", replace_all=True)
    check("edit_file diff is kept short", r["ok"] and r["data"]["diff"].count("\n") <= 45 and "truncated" in r["data"]["diff"], str(r)[:200])

    # --- glob_files ---------------------------------------------------------------------------
    for name, body in (("app/alpha.py", "def add(a, b):\n    return a + b\n"),
                       ("app/beta.py", "DEBUG = True\n\ndef run():\n    return 'beta'\n"),
                       ("app/gamma.py", "def mul(a, b):\n    return a * b\n"),
                       ("app/readme.txt", "debug notes (lower case)\n")):
        ft.write_file(name, body)
    r = ft.glob_files("app/*.py")
    check("glob_files lists matching files", r["ok"] and r["data"]["matches"] == ["app/alpha.py", "app/beta.py", "app/gamma.py"], str(r))
    r = ft.glob_files("**/*.py")
    check("glob_files ** recurses", "pkg/sub/deep.py" in r["data"]["matches"] and "app/beta.py" in r["data"]["matches"], str(r))
    check("glob_files returns files, not directories", "app" not in ft.glob_files("*")["data"]["matches"])
    check("glob_files absolute pattern rejected", not ft.glob_files("/etc/*")["ok"])
    check("glob_files '..' pattern rejected", not ft.glob_files("../*")["ok"])
    check("glob_files windows drive pattern rejected", not ft.glob_files("C:\\*")["ok"])
    r = ft.glob_files("**/*.py", max_results=2)
    check("glob_files max_results truncates", len(r["data"]["matches"]) == 2 and r["data"]["truncated"] and r["data"]["count"] >= 4, str(r))
    check("glob_files no match -> ok with empty list", ft.glob_files("*.nothing")["data"]["matches"] == [])

    # --- search_in_files ----------------------------------------------------------------------
    r = ft.search_in_files("DEBUG", file_pattern="*.py")
    check("search_in_files finds DEBUG only in beta.py", r["ok"] and [m["file"] for m in r["data"]["matches"]] == ["app/beta.py"]
          and r["data"]["matches"][0]["line"] == 1, str(r))
    check("search_in_files is case-sensitive by default", len(ft.search_in_files("DEBUG")["data"]["matches"]) == 1)
    check("search_in_files ignore_case", len(ft.search_in_files("debug", ignore_case=True)["data"]["matches"]) == 2)
    r = ft.search_in_files("DEBUG", file_pattern="*.txt")
    check("search_in_files file_pattern restricts the files", r["ok"] and r["data"]["matches"] == [], str(r))
    r = ft.search_in_files("^def (add|mul)", file_pattern="app/*.py", use_regex=True)
    check("search_in_files regex", [m["file"] for m in r["data"]["matches"]] == ["app/alpha.py", "app/gamma.py"], str(r))
    check("search_in_files invalid regex -> error", not ft.search_in_files("(", use_regex=True)["ok"])
    check("search_in_files literal text containing regex characters", ft.search_in_files("(a, b)")["data"]["match_count"] == 2)
    check("search_in_files empty pattern rejected", not ft.search_in_files("")["ok"])
    (root / "blob.dat").write_bytes(b"DEBUG\x00\x01\x02")
    check("search_in_files skips binary files", all(m["file"] != "blob.dat" for m in ft.search_in_files("DEBUG")["data"]["matches"]))
    r = ft.search_in_files("ROW", file_pattern="long.txt", max_results=3)
    check("search_in_files max_results truncates but still counts", len(r["data"]["matches"]) == 3 and r["data"]["truncated"] and r["data"]["match_count"] == 200, str(r)[:200])
    check("search_in_files matches a relative-path glob", ft.search_in_files("DEBUG", file_pattern="app/*.py")["data"]["match_count"] == 1)

    # --- bash + safety gate ---------------------------------------------------------------------
    r = ft.bash("echo hello")
    check("bash runs a safe command", r["ok"] and "hello" in r["data"]["stdout"] and r["data"]["executed"], str(r))
    (root / "victim").mkdir()
    (root / "victim" / "keep.txt").write_text("keep me", encoding="utf-8")
    r = ft.bash("rm -rf victim")
    check("bash blocks rm -rf and does not execute it", not r["ok"] and r["data"]["executed"] is False
          and (root / "victim" / "keep.txt").exists() and "blocked by safety gate" in r["error"], str(r))
    r = ft.bash("echo hi; rm -rf victim")
    check("bash blocks a destructive command chained after a safe one", not r["ok"] and (root / "victim").exists(), str(r))
    r = ft.bash("mkdir newdir")
    check("bash blocks an unlisted command by default", not r["ok"] and not (root / "newdir").exists(), str(r))
    ft_auto = FileTools(root, auto_approve=True)
    r = ft_auto.bash("mkdir newdir")
    check("bash allows an unlisted command when the harness sets auto_approve", r["ok"] and (root / "newdir").is_dir(), str(r))
    r = ft_auto.bash("rm -rf victim")
    check("auto_approve does NOT unlock a destructive command", not r["ok"] and (root / "victim" / "keep.txt").exists(), str(r))
    check("bash empty command -> error", not ft.bash("")["ok"])

    # --- the tools plug into the HW5 execute_tool / schemas -----------------------------------------
    check("registry has exactly the six tools", sorted(ft.registry()) == sorted(TOOL_NAMES) and len(TOOL_NAMES) == 6)
    check("a schema exists for every tool", [s["name"] for s in TOOL_SCHEMAS] == list(TOOL_NAMES))
    bash_schema = next(s for s in TOOL_SCHEMAS if s["name"] == "bash")
    check("bash schema exposes only 'command' (the model cannot confirm or auto_approve)",
          list(bash_schema["parameters"]["properties"]) == ["command"])
    check("every tool returns the {ok, data, error} envelope", all(
        set(fn(**args)) == {"ok", "data", "error"} for fn, args in (
            (ft.read_file, {"path": "notes.txt"}), (ft.glob_files, {"pattern": "*"}), (ft.read_file, {"path": "nope"}))))
    try:
        sys.path.insert(0, str(REPO_ROOT / "mcp_servers"))
        from execute_tool import execute_tool  # noqa: E402
        out = json.loads(execute_tool("read_file", {"path": "notes.txt", "max_lines": 1}, tools=ft.registry()))
        check("works through the HW5 execute_tool(tools=...)", out["ok"] and out["data"]["content"] == "line1", str(out))
        out = json.loads(execute_tool("read_file", {"path": "../x"}, tools=ft.registry()))
        check("execute_tool returns the sandbox error without raising", out["ok"] is False, str(out))
        out = json.loads(execute_tool("read_file", {"pth": "notes.txt"}, tools=ft.registry()))
        check("execute_tool survives a malformed call (wrong argument name)", out["ok"] is False, str(out))
    except ImportError as exc:
        print(f"[SKIP] execute_tool integration ({exc})")

passed = sum(1 for _, ok in results if ok)
print(f"\n{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
