"""HW6 Part 4: verify that a function follows the instructions in AGENT.md.

The rules checked here are the ones AGENT.md states in "Coding conventions" and "Testing approach":

  R1 every function has type hints on all parameters and on the return value
  R2 every function has a one-line docstring that starts with a capital letter and ends with a period
  R3 snake_case for functions/variables, UPPER_SNAKE_CASE for module-level constants
  R4 invalid input raises ValueError (message given); no bare 'except:'; no TypeError raised
  R5 no print() calls in library code
  R6 tests named test_<function>_<case> exist and pass offline
  R7 the function behaves as specified (fixed cases)

    python scripts/check_agent_md_compliance_hw06.py --reference          # src/notice_text.py + tests
    python scripts/recorded_run_hw06.py -- python scripts/check_agent_md_compliance_hw06.py --generate
                                      # asks the local model to write the function with AGENT.md/MEMORY.md in its system prompt
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGET = "normalize_notice_title"
SNAKE = re.compile(r"^_*[a-z][a-z0-9_]*$|^_+$")
UPPER = re.compile(r"^[A-Z][A-Z0-9_]*$")

TASK = (
    f"Write a Python function `{TARGET}(title, max_length=100)` for recall notice titles. It trims the title, "
    "collapses every run of whitespace into one space, and returns the cleaned title. It raises ValueError when the "
    "title is not a string, is empty after trimming, or is longer than max_length after cleaning. "
    f"Also write test functions for it. Reply with ONE Python code block that contains the function, any imports and "
    "constants, and the tests."
)


# --------------------------------------------------------------------------- AST rules
def all_functions(tree: ast.AST) -> List[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def rule_type_hints(tree: ast.AST) -> Tuple[bool, str]:
    missing: List[str] = []
    for fn in all_functions(tree):
        args = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
        for arg in args:
            if arg.arg in ("self", "cls"):
                continue
            if arg.annotation is None:
                missing.append(f"{fn.name}({arg.arg})")
        for extra in (fn.args.vararg, fn.args.kwarg):
            if extra is not None and extra.annotation is None:
                missing.append(f"{fn.name}(*{extra.arg})")
        if fn.returns is None:
            missing.append(f"{fn.name} -> return")
    return not missing, "all annotated" if not missing else "missing: " + ", ".join(missing)


def rule_docstrings(tree: ast.AST) -> Tuple[bool, str]:
    problems: List[str] = []
    for fn in all_functions(tree):
        doc = ast.get_docstring(fn)
        if not doc:
            problems.append(f"{fn.name}: no docstring")
            continue
        if "\n" in doc.strip():
            problems.append(f"{fn.name}: docstring is not one line")
        elif not doc.strip()[0].isupper():
            problems.append(f"{fn.name}: docstring does not start with a capital letter")
        elif not doc.strip().endswith("."):
            problems.append(f"{fn.name}: docstring does not end with a period")
    return not problems, "all one-line, capitalised, end with '.'" if not problems else "; ".join(problems)


def rule_naming(tree: ast.Module) -> Tuple[bool, str]:
    problems: List[str] = []
    for fn in all_functions(tree):
        if not SNAKE.match(fn.name):
            problems.append(f"function {fn.name}")
        for arg in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs:
            if not SNAKE.match(arg.arg):
                problems.append(f"parameter {arg.arg}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and not SNAKE.match(node.id) and not UPPER.match(node.id):
            problems.append(f"variable {node.id}")
    for node in tree.body:  # module-level assignments are constants
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for target in targets:
            if isinstance(target, ast.Name) and not UPPER.match(target.id):
                problems.append(f"module constant {target.id} is not UPPER_SNAKE_CASE")
    return not problems, "snake_case / UPPER_SNAKE_CASE ok" if not problems else "; ".join(sorted(set(problems)))


def rule_errors(tree: ast.AST) -> Tuple[bool, str]:
    problems: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            problems.append("bare except")
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            name = exc.id if isinstance(exc, ast.Name) else getattr(exc, "attr", "")
            if name == "TypeError":
                problems.append("raises TypeError instead of ValueError")
    target = next((fn for fn in all_functions(tree) if fn.name == TARGET), None)
    if target is None:
        problems.append(f"function {TARGET} not found")
    else:
        raises = [n for n in ast.walk(target) if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
                  and getattr(n.exc.func, "id", "") == "ValueError" and n.exc.args]
        if not raises:
            problems.append(f"{TARGET} never raises ValueError with a message")
    return not problems, "ValueError with messages, no bare except" if not problems else "; ".join(problems)


def rule_no_print(tree: ast.AST) -> Tuple[bool, str]:
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print"]
    return not calls, "no print() calls" if not calls else f"{len(calls)} print() call(s)"


# --------------------------------------------------------------------------- execution rules
def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def run_tests(modules: List[Any]) -> Tuple[bool, str]:
    tests: List[Tuple[str, Callable[[], None]]] = []
    for module in modules:
        tests += [(n, f) for n, f in vars(module).items() if n.startswith(f"test_{TARGET}_") and callable(f)]
    if not tests:
        return False, f"no test function named test_{TARGET}_<case>"
    failures: List[str] = []
    for name, func in tests:
        try:
            func()
        except Exception as exc:  # noqa: BLE001 - report any failure of a test
            failures.append(f"{name}: {exc.__class__.__name__}: {exc}")
    return not failures, f"{len(tests) - len(failures)}/{len(tests)} tests pass" + ("" if not failures else " - " + "; ".join(failures))


def behaviour(function: Callable[..., Any]) -> Tuple[bool, str]:
    problems: List[str] = []
    cases = [("  Frozen \t Berries\nRecall  ", None, "Frozen Berries Recall"), ("Ok", None, "Ok"), ("x" * 100, None, "x" * 100),
             ("abcde", 5, "abcde")]
    for value, limit, expected in cases:
        try:
            got = function(value) if limit is None else function(value, limit)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{value!r} raised {exc.__class__.__name__}")
            continue
        if got != expected:
            problems.append(f"{value!r} -> {got!r}, expected {expected!r}")
    for value, limit in [("", None), ("   ", None), (123, None), (None, None), ("x" * 101, None), ("abcdef", 5)]:
        try:
            function(value) if limit is None else function(value, limit)
            problems.append(f"{value!r} should raise ValueError")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{value!r} raised {exc.__class__.__name__} instead of ValueError")
    return not problems, "10/10 behaviour cases" if not problems else "; ".join(problems)


def check_files(files: List[Path]) -> List[Dict[str, Any]]:
    source = "\n\n".join(f.read_text(encoding="utf-8") for f in files)
    results: List[Dict[str, Any]] = []
    trees = [(f, ast.parse(f.read_text(encoding="utf-8"))) for f in files]

    def over_files(rule: Callable[[ast.Module], Tuple[bool, str]]) -> Tuple[bool, str]:
        parts = [rule(tree) for _, tree in trees]
        return all(ok for ok, _ in parts), "; ".join(msg for ok, msg in parts if not ok) or parts[0][1]

    combined = ast.parse(source)
    for rule_id, text, rule in [
        ("R1", "type hints on every parameter and return value", rule_type_hints),
        ("R2", "one-line capitalised docstring ending with a period", rule_docstrings),
        ("R3", "snake_case names / UPPER_SNAKE_CASE constants", rule_naming),
        ("R4", "ValueError for invalid input, no bare except", rule_errors),
        ("R5", "no print() in library code", rule_no_print),
    ]:
        ok, detail = rule(combined)
        results.append({"rule": rule_id, "instruction": text, "passed": ok, "detail": detail})
    try:
        modules = [load_module(f, f"_checked_{i}") for i, f in enumerate(files)]
        target = next(getattr(m, TARGET) for m in modules if hasattr(m, TARGET))
        ok, detail = run_tests(modules)
        results.append({"rule": "R6", "instruction": f"tests named test_{TARGET}_<case> exist and pass", "passed": ok, "detail": detail})
        ok, detail = behaviour(target)
        results.append({"rule": "R7", "instruction": "function behaves as specified", "passed": ok, "detail": detail})
    except Exception as exc:  # noqa: BLE001
        results.append({"rule": "R6", "instruction": "code loads and tests run", "passed": False, "detail": f"{exc.__class__.__name__}: {exc}"})
        results.append({"rule": "R7", "instruction": "function behaves as specified", "passed": False, "detail": "code did not load"})
    return results


def print_results(title: str, results: List[Dict[str, Any]]) -> bool:
    print(f"\n=== {title} ===")
    for r in results:
        print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['rule']} {r['instruction']}: {r['detail']}")
    ok = all(r["passed"] for r in results)
    print(f"-> {'FOLLOWS' if ok else 'DOES NOT FOLLOW'} AGENT.md ({sum(r['passed'] for r in results)}/{len(results)} rules)")
    return ok


# --------------------------------------------------------------------------- generation
def extract_code(reply: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", reply, flags=re.S)
    return max(blocks, key=len).strip() + "\n" if blocks else reply.strip() + "\n"


def generate(model: str, base_url: str, attempts: int) -> int:
    from src.file_memory import build_system_prompt, load_memory_files
    from src.model_client import ModelClientError, OllamaModelClient

    raw = ROOT / "reports/hw06/raw"
    raw.mkdir(parents=True, exist_ok=True)
    agent_text, memory_text = load_memory_files(ROOT / "AGENT.md", ROOT / "MEMORY.md")
    system = build_system_prompt(agent_text, memory_text)
    client = OllamaModelClient(model=model, base_url=base_url, timeout_seconds=1800)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": TASK}]
    log: List[Dict[str, Any]] = []
    ok = False
    for attempt in range(1, attempts + 1):
        print(f"\nAttempt {attempt}: asking {model} (AGENT.md and MEMORY.md are in the system prompt) ...")
        try:
            reply = client.complete(messages).content
        except ModelClientError as exc:
            print(f"ERROR: {exc}")
            return 2
        code = extract_code(reply)
        path = raw / "generated_normalize_notice_title.py"
        path.write_text(code, encoding="utf-8")
        print("----- generated code -----\n" + code)
        try:
            results = check_files([path])
        except SyntaxError as exc:
            results = [{"rule": "R0", "instruction": "code parses", "passed": False, "detail": str(exc)}]
        ok = print_results(f"Attempt {attempt}: generated function vs AGENT.md", results)
        log.append({"attempt": attempt, "code": code, "results": results, "passed": ok})
        if ok:
            break
        problems = "; ".join(f"{r['rule']}: {r['detail']}" for r in results if not r["passed"])
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": f"The code breaks these AGENT.md rules: {problems}. Fix them and reply with ONE corrected Python code block."}]
    (raw / "agent_md_compliance.json").write_text(json.dumps({"model": model, "attempts": log, "final_passed": ok}, indent=2), encoding="utf-8")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", action="store_true", help="check src/notice_text.py and its tests")
    parser.add_argument("--generate", action="store_true", help="ask the local model to write the function, then check it")
    parser.add_argument("--file", type=Path, action="append", help="check these files instead")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--attempts", type=int, default=4)
    args = parser.parse_args()
    print("AGENT.md compliance check - Sharan Lourduraj (SID4 9619)")
    status = 0
    if args.reference or args.file or not args.generate:
        files = args.file or [ROOT / "src/notice_text.py", ROOT / "tests/test_notice_text_hw06.py"]
        results = check_files(files)
        ok = print_results("Reference implementation: " + ", ".join(str(f.relative_to(ROOT)) if f.is_absolute() and ROOT in f.parents else str(f) for f in files), results)
        (ROOT / "reports/hw06/raw").mkdir(parents=True, exist_ok=True)
        (ROOT / "reports/hw06/raw/agent_md_compliance_reference.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        status |= 0 if ok else 1
    if args.generate:
        status |= generate(args.model, args.base_url, args.attempts)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
