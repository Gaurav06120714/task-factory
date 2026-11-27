"""Free, local backend for the generator: Ollama, driven in small steps.

A 7B model cannot browse files, run tools or reliably edit existing code, so the factory
does that for it. Each feature is ONE new module; the factory adds the export line.
Steps, each a separate short prompt that returns one whole file:
  1. implementation  -> checked by importing it
  2. tests           -> the model only picks test INPUTS (Python expressions); the factory
                        runs each one against the implementation and records the real result
                        or exact error as the expected value. A 7B model cannot predict
                        outputs reliably; it can choose varied inputs. Mutation testing
                        (factory/mutate.py) then measures whether those tests are strong.
  3. requirement doc -> TASK_INSTRUCTION.md, written from the code and tests

Env: TF_OLLAMA_MODEL (default qwen2.5-coder:7b), TF_OLLAMA_URL, TF_OLLAMA_CTX.
"""

import ast
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path

URL = os.environ.get("TF_OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("TF_OLLAMA_MODEL", "qwen2.5-coder:7b")
CTX = int(os.environ.get("TF_OLLAMA_CTX", "32768"))
MAX_FILE_CHARS = 60_000
MAX_TOKENS = int(os.environ.get("TF_OLLAMA_MAX_TOKENS", "4096"))


def chat(prompt: str, json_mode: bool = False, timeout: int = 1800, temperature: float = 0.2) -> str:
    body = {"model": MODEL, "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            # num_predict: a 7B model sometimes loops forever; ~3 min at 22 tok/s, then give up
            "options": {"num_ctx": CTX, "temperature": temperature, "num_predict": MAX_TOKENS}}
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(f"{URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


# ---------------------------------------------------------------- repo context

FENCE_RE = re.compile(r"^\s*```[\w+-]*\n(.*?)\n?```\s*$", re.S)
MIN_TESTS = 3
TEMPS = (0.2, 0.6, 0.9)


def unfence(body: str) -> str:
    """Small models wrap file bodies in markdown fences; strip them."""
    body = body.strip("\n")
    m = FENCE_RE.match(body)
    body = m.group(1) if m else body
    return re.sub(r"\n```\s*$", "", body).rstrip() + "\n"


def sh(cmd: str, repo: Path, env: dict) -> tuple[bool, str]:
    try:  # stdin closed + timeout: a test waiting for terminal input fails fast instead of hanging
        p = subprocess.run(cmd, shell=True, cwd=repo, env=env, capture_output=True, text=True,
                           timeout=180, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "timed out after 180s (probably waiting for input or looping)"
    return p.returncode == 0, (p.stdout + p.stderr)[-4000:]


FAILED_RE = re.compile(r"^(?:FAILED|ERROR) \S+?::(\w+)", re.M)


def drop_failing(source: str, output: str) -> tuple[str, int]:
    """Remove top-level test functions pytest reported as failed. Returns (source, tests left)."""
    failing = set(FAILED_RE.findall(output))
    tree = ast.parse(source)
    tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test")]
    lines = source.splitlines(keepends=True)
    for n in sorted((n for n in tests if n.name in failing), key=lambda n: -n.lineno):
        first = min([n.lineno] + [d.lineno for d in n.decorator_list]) - 1
        del lines[first:n.end_lineno]
    # ponytail: top-level test functions only; failing methods inside test classes are not dropped
    return "".join(lines), len([n for n in tests if n.name not in failing])


UNDEFINED_RE = re.compile(r"undefined name '(\w+)'")


def add_missing_imports(code: str, lint_output: str, export_text: str, extra: dict) -> str:
    """Small models forget imports. Add the obvious ones: stdlib modules, the package's own
    public names (from its export file) and names the repo config maps (e.g. `_`)."""
    # ponytail: Python only; other languages would need their own import fixer
    where = {m.group(2): m.group(1) for m in re.finditer(r"from (\.\w+) import (\w+)", export_text)}
    lines = []
    for name in dict.fromkeys(UNDEFINED_RE.findall(lint_output)):
        if name in extra:
            lines.append(extra[name])
        elif name in sys.stdlib_module_names:
            lines.append(f"import {name}")
        elif name in where:
            lines.append(f"from {where[name]} import {name}")
    if not lines:
        return code
    head, sep, rest = code.partition("from __future__ import annotations\n")
    return (head + sep + "\n".join(lines) + "\n" + rest) if sep else "\n".join(lines) + "\n" + code


def example(cfg: dict) -> dict:
    """The first validated task of this repo, shown to the model as the quality bar."""
    from factory.build import ROOT
    specs = sorted((ROOT / "specs" / cfg["name"]).glob("*/solution.patch"))
    if not specs:
        return {"code": "", "tests": ""}
    spec = specs[0].parent
    code = "\n".join(l[1:] for l in (spec / "solution.patch").read_text().splitlines()
                     if l.startswith("+") and not l.startswith("+++"))
    tests = "\n".join(f.read_text() for f in sorted((spec / "feature").rglob("*.py")))
    return {"code": f"\nExample of good code from an earlier task:\n{code}\n",
            "tests": f"\nExample of a good test file from an earlier task:\n{tests}\n"}


IMPL = """You are adding ONE new feature to the {name} library ({language}).

Feature: {title}
{summary}

Write the complete new module {mod_path}. It must define `{symbol}`, be self-contained
(standard library plus {name}'s own API), follow the library's style (type hints, docstrings)
and reject bad input with clear errors and exact messages. The factory exports it as {name}.{symbol}.
{local_impl_hint}
{ex}
Where {name}'s public names live (import ONLY names listed here):
{api}

Reply with ONLY the content of {mod_path}."""

CASES = """Choose test inputs for a new feature of the {name} library.

Feature: {title}
{summary}

The implementation ({mod_path}, available as {name}.{symbol}):
{impl}
{hint}
Reply with a JSON object {{"cases": [...]}} holding 10 to 16 cases. Each case is
{{"name": "short_snake_case_name", "expr": "<ONE Python expression that uses {name}.{symbol}>"}}.
- Cover normal use, edge cases (boundaries, empty, unusual but valid input) and EVERY error the code can raise.
- Each expr is a single expression: no statements, assignments or imports. Only `{name}` is available.
- {local_case_hint}
- Do NOT write expected values: the factory runs every expression and records what it returns or raises."""

INSTR = """Write the requirement document for this feature of {name}, as a feature request a
developer receives. They will NOT see the code or tests below, yet their own implementation
must pass these tests.

Feature: {title}
Implementation:
{impl}
Tests:
{tests}

Specify precisely: that it is available as {name}.{symbol} (do not say which file it lives in);
its signature; behaviour for normal input and for every edge case the tests check; every exact
error message or output the tests check (quote them). Use markdown headings and bullet lists.
Copy every message exactly as the tests expect it, including its quote characters (Python repr
uses single quotes). Describe ONLY behaviour this implementation really has: read the code, and check every example,
accepted format and unit you mention against it. Do NOT include code from the implementation
and do not mention test files.

Reply with ONLY the markdown document."""


RECORD = """import importlib, json, sys
pkg = importlib.import_module(sys.argv[1])
out = []
for c in json.load(open(sys.argv[2])):
    try:
        v = eval(c["expr"], {sys.argv[1]: pkg})
        out.append({"repr": repr(v)})
    except Exception as e:
        out.append({"module": type(e).__module__, "type": type(e).__name__, "msg": str(e)})
print(json.dumps(out))
"""


def parse_cases(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    cases = data.get("cases", []) if isinstance(data, dict) else data
    seen, out = set(), []
    for c in cases if isinstance(cases, list) else []:
        expr = str(c.get("expr", "")).strip() if isinstance(c, dict) else ""
        try:
            ast.parse(expr, mode="eval")
        except SyntaxError:
            continue
        if expr and expr not in seen:
            seen.add(expr)
            out.append({"name": re.sub(r"\W+", "_", str(c.get("name") or "case")).strip("_").lower()[:40] or "case",
                        "expr": expr})
    return out


def render_tests(pkg: str, symbol: str, cases: list[dict], results: list[dict]) -> str:
    """pytest file whose expected values are what the reference implementation really did."""
    lines = [f'"""Tests for {pkg}.{symbol}. Inputs chosen by the generator; expected values recorded',
             'from the reference implementation."""', "import re", "", "import pytest", "", f"import {pkg}", ""]
    names: dict[str, int] = {}
    for c, r in zip(cases, results):
        if " at 0x" in r.get("repr", "") + r.get("msg", ""):
            continue  # memory addresses are not reproducible
        if "repr" not in r and r.get("type") == "AttributeError" and symbol in r.get("msg", ""):
            continue  # the expression does not even reach the feature
        n = names[c["name"]] = names.get(c["name"], 0) + 1
        name = c["name"] + (f"_{n}" if n > 1 else "")
        lines += ["", f"def test_{name}():"]
        if "repr" in r:
            lines.append(f"    assert repr({c['expr']}) == {r['repr']!r}")
        else:
            exc = r["type"] if r["module"] == "builtins" else (f"{pkg}.{r['type']}" if r["module"].startswith(pkg) else "Exception")
            lines += [f"    with pytest.raises({exc}, match=re.escape({r['msg']!r})):", f"        {c['expr']}"]
    return "\n".join(lines) + "\n"


def run(cfg: dict, repo: Path, env: dict, proposal: dict, test_file: str, rounds: int, log,
        problems: list[str] | None = None) -> None:
    """Build the feature in the worktree step by step. problems: validator feedback from a
    previous attempt; then only the tests and the instruction are redone."""
    ex = example(cfg)
    f = {"local_impl_hint": "", "local_case_hint": "Call the feature directly with literal arguments.", "python": sys.executable, **cfg, **proposal, "mod_path": cfg["new_module"].format(module=proposal["module"]),
         "test_path": f"{cfg['test_dir']}/{test_file}"}
    mod, test = repo / f["mod_path"], repo / f["test_path"]

    def ask(step: str, prompt: str, round_: int = 0, json_mode: bool = False) -> str | None:
        try:  # each retry samples hotter, so the model does not repeat the same mistake
            reply = chat(prompt, json_mode=json_mode, timeout=900, temperature=TEMPS[min(round_, len(TEMPS) - 1)])
            return reply if json_mode else unfence(reply)
        except (TimeoutError, OSError) as e:  # a slow reply is a failed round, not a dead task
            log("local_step", step=step, error=f"model call failed: {e}")
            return None

    if problems is None:  # 1. implementation
        export = repo / cfg["export_file"]
        export.write_text(export.read_text() + cfg["export_line"].format(**f) + "\n")
        api = "\n".join(l for l in export.read_text().splitlines() if "import" in l)
        prompt = IMPL.format(**f, ex=ex["code"], api=api)
        for i in range(rounds + 1):
            if (code := ask("impl", prompt, i)) is None:
                continue
            mod.parent.mkdir(parents=True, exist_ok=True)
            mod.write_text(code)
            ok, out = sh(cfg["import_check"].format(**f), repo, env)
            if not ok and UNDEFINED_RE.search(out):
                mod.write_text(code := add_missing_imports(code, out, export.read_text(), cfg.get("auto_imports", {})))
                ok, out = sh(cfg["import_check"].format(**f), repo, env)
            log("local_step", step="impl", round=i, ok=ok)
            if ok:
                break
            error = next((l for l in reversed(out.splitlines()) if l.strip()), out)
            log("local_step", step="impl_error", error=error[:300])
            prompt = (f"IMPORTANT: a previous attempt failed with this error, avoid it:\n{error}\n\n"
                      + IMPL.format(**f, ex=ex["code"], api=api))
        else:
            return

    impl = mod.read_text() if mod.exists() else ""
    # 2. tests: the model picks inputs, the implementation supplies the expected values
    hint = ("Problems found in the previous attempt, avoid them:\n" + "\n".join(problems) + "\n") if problems else ""
    for i in range(rounds + 1):
        if (raw := ask("cases", CASES.format(**f, impl=impl, hint=hint), i, json_mode=True)) is None:
            continue
        cases = parse_cases(raw)
        cases_file = repo / ".tf_cases.json"
        cases_file.write_text(json.dumps(cases))
        ok, out = sh(f"python -c {shlex.quote(RECORD)} {cfg['name']} {cases_file}", repo, env)
        cases_file.unlink()
        try:
            results = json.loads(out.strip().splitlines()[-1]) if ok else []
        except (json.JSONDecodeError, IndexError):
            results = []
        test.write_text(render_tests(cfg["name"], proposal["symbol"], cases, results))
        ok, out = sh(cfg["host_test_cmd"].format(path=f["test_path"]), repo, env)
        if not ok:  # e.g. output that changes between runs: drop those tests
            kept, _ = drop_failing(test.read_text(), out)
            test.write_text(kept)
        left = test.read_text().count("\ndef test_")
        log("local_step", step="tests", round=i, cases=len(cases), recorded=len(results), tests=left)
        if left >= MIN_TESTS:
            break
    else:
        return

    # 3. requirement document
    for i in range(rounds + 1):
        doc = ask("instruction", INSTR.format(**f, impl=impl, tests=test.read_text()), i)
        ok = bool(doc) and len(doc) >= 300 and proposal["symbol"] in doc and test_file not in doc
        log("local_step", step="instruction", round=i, ok=ok)
        if ok:
            (repo / "TASK_INSTRUCTION.md").write_text(doc)
            return


def _selfcheck() -> None:
    assert unfence("```python\nx = 1\n```") == "x = 1\n"
    src = ("import pytest\n\ndef test_a():\n    assert 1\n\n\n@pytest.mark.parametrize('x', [1])\n"
           "def test_b(x):\n    assert 0\n\n\ndef test_c():\n    assert 1\n")
    out = "FAILED tests/test_x.py::test_b[1] - assert 0\n"
    kept, left = drop_failing(src, out)
    assert left == 2 and "test_b" not in kept and "parametrize" not in kept and "test_c" in kept, kept
    ast.parse(kept)
    fixed = add_missing_imports("from __future__ import annotations\nx = re.compile(_('a'))\n",
                                "m.py:2:5: undefined name 're'\nm.py:2:16: undefined name '_'\n"
                                "m.py:3:1: undefined name 'ParamType'\n",
                                "from .types import ParamType as ParamType\n",
                                {"_": "from gettext import gettext as _"})
    assert fixed.splitlines()[1:4] == ["import re", "from gettext import gettext as _",
                                       "from .types import ParamType"], fixed
    cases = parse_cases('{"cases": [{"name": "Parses KB!", "expr": "click.X().convert(\'1K\', None, None)"},'
                        '{"name": "bad", "expr": "click.X().convert(\'?\', None, None)"}, {"name": "dup", "expr": "x ="}]}')
    assert [c["name"] for c in cases] == ["parses_kb", "bad"], cases
    body = render_tests("click", "X", cases, [{"repr": "1024"},
                        {"module": "click.exceptions", "type": "BadParameter", "msg": "'?' is bad."}])
    assert "assert repr(click.X().convert('1K', None, None)) == '1024'" in body, body
    assert "pytest.raises(click.BadParameter, match=re.escape(\"'?' is bad.\"))" in body, body
    ast.parse(body)
    print("local_llm selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
