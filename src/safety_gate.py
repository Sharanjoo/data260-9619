"""HW7 Part 6: the bash safety gate. Pure Python, no model, no I/O, no subprocess.

Three layers, each usable and testable on its own:

* ``SAFE_PREFIXES``: an allow-list of read-only command prefixes. A command is "safe"
  only if EVERY piece of it (each part of a ``;`` / ``&&`` / ``||`` / ``|`` chain, each
  ``$(...)`` or backtick substitution, each ``bash -c '...'`` payload) matches a prefix.
* ``is_destructive(command)``: an INDEPENDENT deny-list. It does not consult
  SAFE_PREFIXES. It flags recursive deletion, privilege escalation, permission/ownership
  changes, raw-device writes, filesystem creation and redirection to root paths, looking
  at every piece of the command, not just its first word (``ls; rm -rf /`` is destructive).
* ``confirm_bash(command, auto_approve=False)``: the decision. Destructive commands are
  blocked unless explicit confirmation is supplied (``confirmed=True``), and
  ``auto_approve`` can never override that, even for commands that match SAFE_PREFIXES.

Known limits (this is a guard rail, not a sandbox): it reasons about command text. It cannot
see what a script or an inline interpreter program does (``python -c ...``, ``awk ...``,
``python script.py``): those are ordinary "not on the allow-list" commands, so a caller that
sets ``auto_approve=True`` is trusting them. Commands whose name is built at run time, or that
feed a shell from stdin or a script, are refused unless explicitly confirmed. Reading
sensitive files with SAFE_PREFIXES commands (``cat /etc/shadow``) is not restricted here;
file access is confined by the sandbox directory in the file tools, not by this gate.
"""
from __future__ import annotations

import re
import shlex
from typing import Dict, List, Optional, Tuple

# --- allow-list ------------------------------------------------------------------------

# Read-only commands. Matching is by whole tokens, so "ls" matches "ls -la" but not "lsof",
# and "git status" matches "git status -s" but not "git stash". A prefix NEVER makes a
# command safe on its own: see is_safe_command() for the other conditions.
SAFE_PREFIXES: Tuple[str, ...] = (
    "ls", "dir", "pwd", "echo", "cat", "type", "head", "tail", "wc", "grep",
    "git status", "git log", "git diff", "git show", "git branch",
    "python --version", "python3 --version", "pip list",
)

MAX_COMMAND_LENGTH = 4000
_SUB_MARK = "\x01"  # stands in for a $(...) / `...` body inside a segment
_MAX_DEPTH = 6  # nesting depth of $(...) / bash -c; deeper than this fails closed

# --- deny-list data ----------------------------------------------------------------------

_PRIV_ESC = {"sudo", "su", "doas", "pkexec", "runas", "gsudo", "sudoedit", "run0"}
_PERMS = {"chmod", "chown", "chgrp", "setfacl", "chattr", "icacls", "takeown", "cacls", "set-acl"}
_MKFS_EXACT = {"mkfs", "mke2fs", "mkswap", "mkntfs", "newfs", "newfs_msdos", "mkdosfs",
               "mformat", "format", "format-volume", "diskpart"}
_RAW_DEVICE_TOOLS = {"fdisk", "sfdisk", "cfdisk", "parted", "gdisk", "sgdisk", "wipefs", "blkdiscard"}
_REMOVERS = {"rm", "del", "erase", "rmdir", "rd", "remove-item", "ri"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh", "ash",
           "cmd", "powershell", "pwsh"}
_RESERVED = {"{", "}", "!", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "coproc"}
_WRAPPERS = {"env", "nohup", "time", "command", "exec", "nice", "ionice", "stdbuf", "timeout",
             "watch", "builtin", "setsid", "chronic", "busybox"}
_EMBEDDERS = {"xargs", "parallel", "find", "fd"}  # run another command given in their arguments
_DEV_WRITERS = {"cp", "mv", "tee", "install", "rsync", "truncate", "ln"}
_HARMLESS_DEV = {"/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr", "/dev/stdin", "/dev/tty", "/dev/full"}
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WIN_ABS = re.compile(r"^[A-Za-z]:[\\/]")


# --- shell-ish parsing --------------------------------------------------------------------

def _read_paren(s: str, i: int) -> Tuple[str, int]:
    """s[i-1] is '(' of a $( ... ). Return (inner text, index just past the matching ')')."""
    depth, j, quote = 1, i, None
    while j < len(s):
        c = s[j]
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"':
                j += 1
        elif c in "'\"":
            quote = c
        elif c == "\\":
            j += 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return s[i:j], j + 1
        j += 1
    return s[i:], len(s)  # unterminated: take the rest, fail toward analysing more text


def _split(cmd: str) -> Tuple[List[str], List[str]]:
    """Split a command line into (segments, substitutions).

    Segments are the pieces separated by unquoted ; & && | || newlines and parentheses.
    Substitutions are the bodies of $(...) and `...` (active unquoted and inside double
    quotes, inactive inside single quotes), each to be analysed as a command in its own right.
    """
    segs: List[str] = []
    subs: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    i, n = 0, len(cmd)

    def flush() -> None:
        seg = "".join(buf).strip()
        if seg:
            segs.append(seg)
        buf.clear()

    while i < n:
        c = cmd[i]
        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            buf.append(c + cmd[i + 1])
            i += 2
            continue
        if c == "$" and cmd[i + 1:i + 2] == "(":
            if cmd[i + 2:i + 3] == "(":  # $(( arithmetic )): not a command
                end = cmd.find("))", i + 3)
                end = n if end == -1 else end + 2
                buf.append("0")
                i = end
                continue
            inner, i = _read_paren(cmd, i + 2)
            subs.append(inner)
            buf.append(_SUB_MARK)
            continue
        if c == "`":
            j = cmd.find("`", i + 1)
            j = n if j == -1 else j
            subs.append(cmd[i + 1:j])
            buf.append(_SUB_MARK)
            i = j + 1
            continue
        if quote == '"':
            buf.append(c)
            if c == '"':
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
            buf.append(c)
            i += 1
            continue
        if c in ";\n\r":
            flush()
            i += 1
            continue
        if c in "&|":
            prev = cmd[i - 1] if i else ""
            nxt = cmd[i + 1] if i + 1 < n else ""
            if (c == "&" and (prev in "<>" or nxt == ">")) or (c == "|" and prev == ">"):
                buf.append(c)  # 2>&1, >&2, &>file, >|file: part of a redirect, not a separator
                i += 1
                continue
            flush()
            i += 2 if nxt == c else 1
            continue
        if c in "()":
            flush()
            i += 1
            continue
        buf.append(c)
        i += 1
    flush()
    return segs, subs


def _strip_redirects(seg: str) -> Tuple[str, List[str]]:
    """Remove unquoted output redirections (>, >>, >|, &>, n>) from a segment.
    Returns (segment without them, list of raw redirect targets)."""
    out: List[str] = []
    targets: List[str] = []
    quote: Optional[str] = None
    i, n = 0, len(seg)
    while i < n:
        c = seg[i]
        if quote:
            out.append(c)
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < n:
                out.append(seg[i + 1])
                i += 1
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(seg[i:i + 2])
            i += 2
            continue
        if c in "'\"":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == ">" or (c == "&" and seg[i + 1:i + 2] == ">"):
            # drop a preceding file-descriptor number (2>, 1>>) from the command text
            while out and out[-1].isdigit() and (len(out) == 1 or out[-2].isspace()):
                out.pop()
            if c == "&":  # &>file / &>>file
                i += 1
            i += 1  # the '>'
            if i < n and seg[i] in ">|":  # >>  >|
                i += 1
            if c == ">" and i < n and seg[i] == "&":
                j = i + 1
                if j < n and (seg[j].isdigit() or seg[j] == "-"):  # >&2, >&1-: duplicate a descriptor
                    while j < n and (seg[j].isdigit() or seg[j] == "-"):
                        j += 1
                    i = j
                    out.append(" ")
                    continue
                i += 1  # >&file: redirects both streams to a file
            while i < n and seg[i] in " \t":
                i += 1
            start, tq = i, None
            while i < n:
                ch = seg[i]
                if tq:
                    if ch == tq:
                        tq = None
                elif ch in "'\"":
                    tq = ch
                elif ch.isspace() or ch in "<>":
                    break
                i += 1
            targets.append(seg[start:i].strip("'\""))
            out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out), targets


def _tokens(seg: str) -> List[str]:
    try:
        return shlex.split(seg, posix=True)
    except ValueError:  # unbalanced quotes: crude split still lets the deny-list see "rm -rf"
        return seg.replace("'", " ").replace('"', " ").split()


def _name(tok: str) -> str:
    """Canonical command name: no leading backslash, no directory, lower case, no .exe."""
    t = tok.lstrip("\\")
    t = re.split(r"[\\/]", t)[-1].lower()
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if t.endswith(ext):
            t = t[: -len(ext)]
    return t


# --- deny-list ---------------------------------------------------------------------------

def _redirect_reason(target: str) -> Optional[str]:
    t = target.strip()
    if not t:
        return None
    if t in _HARMLESS_DEV or t.startswith(("/tmp/", "/var/tmp/")):
        return None
    if t.startswith("/dev/") or t.startswith("\\\\.\\"):
        return "raw-device write (output redirected to a device)"
    if t.startswith("/") or _WIN_ABS.match(t) or t.startswith("\\\\"):
        return "redirection to a root path"
    if ".." in re.split(r"[\\/]", t):
        return "redirection to a root path (parent-directory escape)"
    return None


def _device_arg(args: List[str]) -> bool:
    return any(a.startswith("/dev/") and a not in _HARMLESS_DEV for a in args) or any(
        a.startswith("\\\\.\\") or "physicaldrive" in a.lower() for a in args)


def _is_recursive_flag(tok: str) -> bool:
    if tok.startswith("--"):
        return tok.lower() in ("--recursive",)
    return tok.startswith("-") and len(tok) > 1 and any(ch in tok[1:] for ch in "rR")


def _command_start(toks: List[str]) -> int:
    """Index of the real command word: past env assignments, shell keywords and wrappers."""
    i = 0
    while i < len(toks) and _ENV_ASSIGN.match(toks[i]):
        i += 1
    while i < len(toks):
        cmd = _name(toks[i])
        if cmd in _RESERVED:  # `{ rm -rf x; }`, `then rm -rf x`, `do rm -rf $f`
            i += 1
            continue
        if cmd == "function":  # `function f { rm -rf x; }`
            i += 2
            continue
        if cmd in _WRAPPERS:
            i += 1
            while i < len(toks) and (toks[i].startswith("-") or _ENV_ASSIGN.match(toks[i])
                                     or (cmd == "timeout" and re.match(r"^[0-9.]+[smhd]?$", toks[i]))):
                i += 1
            continue
        break
    return i


def _tokens_reason(toks: List[str], depth: int) -> Optional[str]:
    """Deny-list verdict for one already-tokenised simple command."""
    i = _command_start(toks)
    if i >= len(toks):
        return None
    cmd = _name(toks[i])
    args = toks[i + 1:]
    low = [a.lower() for a in args]

    if cmd in _PRIV_ESC:
        return "privilege escalation"
    for k, a in enumerate(low):  # powershell: Start-Process ... -Verb RunAs
        if a == "runas" and k and low[k - 1] == "-verb":
            return "privilege escalation"
    if cmd in _PERMS:
        return "permission/ownership change"
    if cmd in _MKFS_EXACT or cmd.startswith("mkfs."):
        return "filesystem creation"
    if cmd in _RAW_DEVICE_TOOLS:
        return "raw-device write"
    if cmd == "dd" and any(a.lower().startswith("of=") and _device_arg([a[3:]]) for a in args):
        return "raw-device write"
    if cmd in _DEV_WRITERS and _device_arg(args):
        return "raw-device write"
    if cmd == "shred" and _device_arg(args):
        return "raw-device write"
    if cmd == "tee":
        for a in args:
            if not a.startswith("-"):
                r = _redirect_reason(a)
                if r:
                    return r.replace("output redirected to a device", "tee to a device")

    if cmd in _REMOVERS:
        if "--no-preserve-root" in low:
            return "recursive deletion"
        if cmd in ("rm",) and any(_is_recursive_flag(a) for a in args):
            return "recursive deletion"
        if cmd in ("del", "erase", "rd", "rmdir") and any(a in ("/s", "-s") for a in low):
            return "recursive deletion"
        if cmd in ("remove-item", "ri", "rm", "del", "erase", "rd", "rmdir") and any(
                a.startswith("-r") and "-recurse".startswith(a) and len(a) >= 2 for a in low):
            return "recursive deletion"
    if cmd == "find" and any(a in ("-delete",) for a in low):
        return "recursive deletion"
    if cmd == "git" and low[:1] == ["clean"] and any(
            a.startswith("-") and not a.startswith("--") and "d" in a for a in low[1:]):
        return "recursive deletion"
    if cmd == "git" and low[:1] == ["rm"] and any(_is_recursive_flag(a) for a in args[1:]):
        return "recursive deletion"

    if depth >= _MAX_DEPTH:
        return "command nested too deeply to analyse"
    if cmd in _SHELLS:
        for k, a in enumerate(low):
            if a in ("-c", "-command", "/c", "/k", "-lc", "-ic", "-xc", "-ec", "-e") and k + 1 < len(args):
                inner = " ".join(args[k + 1:]) if cmd in ("cmd", "powershell", "pwsh") else args[k + 1]
                r = _command_reason(inner, depth + 1)
                if r:
                    return r
        return None
    if cmd == "eval":
        return _command_reason(" ".join(args), depth + 1)
    if cmd in _EMBEDDERS:  # xargs rm -rf, find . -exec rm -rf {} ;
        for j in range(len(args)):
            r = _tokens_reason(args[j:], depth + 1)
            if r:
                return r
    return None


def _command_reason(command: str, depth: int = 0) -> Optional[str]:
    if depth > _MAX_DEPTH:
        return "command nested too deeply to analyse"
    segs, subs = _split(command)
    for sub in subs:
        r = _command_reason(sub, depth + 1)
        if r:
            return r
    for seg in segs:
        clean, targets = _strip_redirects(seg)
        for t in targets:
            r = _redirect_reason(t)
            if r:
                return r
        r = _tokens_reason(_tokens(clean), depth)
        if r:
            return r
    return None


def destructive_reason(command: str) -> Optional[str]:
    """The deny-list category that matches, or None. Independent of SAFE_PREFIXES."""
    if not isinstance(command, str):
        return "not a string (failing closed)"
    return _command_reason(command)


def is_destructive(command: str) -> bool:
    """True if the command matches the deny-list: recursive deletion, privilege escalation,
    permission/ownership change, raw-device write, filesystem creation, or redirection to a
    root path, in ANY part of the command line."""
    return destructive_reason(command) is not None


# --- commands the gate cannot read ------------------------------------------------------------

_SHELL_INLINE_FLAGS = {"-c", "-command", "/c", "/k", "-lc", "-ic", "-xc", "-ec", "-e"}


def _segment_opacity(toks: List[str]) -> Optional[str]:
    i = _command_start(toks)
    if i >= len(toks):
        return None
    word = toks[i]
    if any(ch in word for ch in "$`*?[{}" + _SUB_MARK):
        return "the command name is built at run time (variable, glob, brace or substitution)"
    cmd = _name(word)
    if cmd in ("source", "."):
        return "it runs a script the gate cannot read (source)"
    if cmd in _SHELLS and not any(a.lower() in _SHELL_INLINE_FLAGS for a in toks[i + 1:]):
        return "it runs a script or standard input in a shell the gate cannot read"
    return None


def opacity_reason(command: str, depth: int = 0) -> Optional[str]:
    """Why the gate cannot analyse this command, or None. Not a deny-list verdict: such a
    command may be harmless, but nothing here can show that, so it needs explicit confirmation."""
    if not isinstance(command, str):
        return "not a string"
    if depth > _MAX_DEPTH:
        return "command nested too deeply to analyse"
    segs, subs = _split(command)
    for sub in subs:
        r = opacity_reason(sub, depth + 1)
        if r:
            return r
    for seg in segs:
        clean, _ = _strip_redirects(seg)
        toks = _tokens(clean)
        r = _segment_opacity(toks)
        if r:
            return r
        i = _command_start(toks)
        if i < len(toks) and _name(toks[i]) in _SHELLS:  # bash -c '<payload>': look inside
            low = [a.lower() for a in toks[i + 1:]]
            for k, a in enumerate(low):
                if a in _SHELL_INLINE_FLAGS and k + 1 < len(low):
                    inner = " ".join(toks[i + 2 + k:]) if _name(toks[i]) in ("cmd", "powershell", "pwsh") else toks[i + 2 + k]
                    r = opacity_reason(inner, depth + 1)
                    if r:
                        return r
    return None


# --- allow-list ----------------------------------------------------------------------------

def _prefix_tokens(prefix: str) -> List[str]:
    return prefix.lower().split()


def _segment_is_safe(seg: str) -> bool:
    clean, targets = _strip_redirects(seg)
    if any(t != "/dev/null" for t in targets):
        return False  # any real redirect is a file write: needs approval
    toks = _tokens(clean)
    if not toks or _ENV_ASSIGN.match(toks[0]):
        return False
    head = [_name(toks[0])] + [t.lower() for t in toks[1:]]
    return any(head[: len(p)] == p for p in map(_prefix_tokens, SAFE_PREFIXES))


def _command_is_safe(command: str, depth: int = 0) -> bool:
    if depth > _MAX_DEPTH:
        return False
    segs, subs = _split(command)
    if not segs:
        return False
    return all(_command_is_safe(s, depth + 1) for s in subs) and all(_segment_is_safe(s) for s in segs)


def is_safe_command(command: str) -> bool:
    """True only if every piece of the command matches SAFE_PREFIXES and nothing in it is
    destructive. A matching first word is never enough on its own."""
    return isinstance(command, str) and not is_destructive(command) and _command_is_safe(command)


# --- the gate --------------------------------------------------------------------------------

def confirm_bash(command: str, auto_approve: bool = False, *, confirmed: bool = False) -> Dict[str, object]:
    """Decide whether a bash command may run. Returns
    ``{"allowed": bool, "reason": str, "destructive": bool}``.

    * Destructive (deny-list) -> BLOCKED unless ``confirmed=True`` (explicit confirmation by a
      human). ``auto_approve`` never overrides this, and a SAFE_PREFIXES match does not either.
    * Every piece matches SAFE_PREFIXES -> allowed.
    * The gate cannot read it (command name built at run time, ``| sh``, ``source``) ->
      BLOCKED unless ``confirmed=True``; ``auto_approve`` does not cover this either.
    * Anything else (not destructive, not on the allow-list) -> blocked unless ``auto_approve``.

    Never executes anything.
    """
    if not isinstance(command, str) or not command.strip():
        return {"allowed": False, "reason": "empty command", "destructive": False}
    if len(command) > MAX_COMMAND_LENGTH or "\x00" in command:
        return {"allowed": False, "reason": "command too long or contains a null byte", "destructive": False}
    why = destructive_reason(command)
    if why is not None:
        if confirmed:
            return {"allowed": True, "reason": f"destructive ({why}) but explicitly confirmed", "destructive": True}
        return {"allowed": False, "reason": f"destructive: {why}; needs explicit confirmation", "destructive": True}
    if _command_is_safe(command):
        return {"allowed": True, "reason": "matches SAFE_PREFIXES", "destructive": False}
    hidden = opacity_reason(command)
    if hidden is not None:
        if confirmed:
            return {"allowed": True, "reason": f"unanalysable ({hidden}) but explicitly confirmed", "destructive": False}
        return {"allowed": False, "reason": f"cannot be analysed: {hidden}; needs explicit confirmation",
                "destructive": False}
    if auto_approve:
        return {"allowed": True, "reason": "not on the allow-list; allowed by auto_approve", "destructive": False}
    return {"allowed": False, "reason": "not on the allow-list; needs approval", "destructive": False}
