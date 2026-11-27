"""Free, local backend for the generator: Ollama, driven in small steps.

A 7B model cannot browse files, run tools or reliably edit existing code, so the factory
does that for it. Each feature is ONE new module; the factory adds the export line.
Steps, each a separate short prompt that returns one whole file:
  1. implementation  -> checked by importing it
  2. tests           -> run on the host; failures go back to the model; tests still
                        failing after the repair rounds are dropped (min MIN_TESTS kept)
  3. requirement doc -> TASK_INSTRUCTION.md, written from the code and tests

Env: TF_OLLAMA_MODEL (default qwen2.5-coder:7b), TF_OLLAMA_URL, TF_OLLAMA_CTX.
"""

import ast
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

URL = os.environ.get("TF_OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("TF_OLLAMA_MODEL", "qwen2.5-coder:7b")
CTX = int(os.environ.get("TF_OLLAMA_CTX", "32768"))
MAX_FILE_CHARS = 60_000


def chat(prompt: str, json_mode: bool = False, timeout: int = 1800) -> str:
    body = {"model": MODEL, "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"num_ctx": CTX, "temperature": 0.2}}
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(f"{URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


# ---------------------------------------------------------------- repo context

OUTLINE_RE = re.compile(r"^\s*(class |def |async def |export |function |struct |namespace )")


def source_files(cfg: dict, repo: Path) -> list[Path]:
    exts = {".py", ".ts", ".js", ".cpp", ".h", ".hpp"}
    out = []
    for p in cfg["source_paths"]:
        base = repo / p
        if base.is_dir():
            out += sorted(f for f in base.rglob("*") if f.suffix in exts)
    return out


def outline(cfg: dict, repo: Path) -> str:
    """Signature lines of every source file, so the model can see the repo's shape."""
    parts = []
    for f in source_files(cfg, repo):
        sigs = [l.rstrip() for l in f.read_text(errors="ignore").splitlines() if OUTLINE_RE.match(l)]
        parts.append(f"## {f.relative_to(repo)}\n" + "\n".join(sigs[:80]))
    return "\n\n".join(parts)



FENCE_RE = re.compile(r"^\s*```[\w+-]*\n(.*?)\n?```\s*$", re.S)
MIN_TESTS = 3


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


def example(cfg: dict) -> dict:
    """The first validated task of this repo, shown to the model as the quality bar."""
    from factory.build import ROOT
    specs = sorted((ROOT / "specs" / cfg["name"]).glob("*/solution.patch"))
    if not specs:
        return {"code": "", "tests": "", "instruction": ""}
    spec = specs[0].parent
    code = "\n".join(l[1:] for l in (spec / "solution.patch").read_text().splitlines()
                     if l.startswith("+") and not l.startswith("+++"))
    tests = "\n".join(f.read_text() for f in sorted((spec / "feature").rglob("*.py")))
    return {"code": f"\nExample of good code from an earlier task:\n{code}\n",
            "tests": f"\nExample of a good test file from an earlier task:\n{tests}\n",
            "instruction": f"\nExample of a good requirement document:\n{(spec / 'instruction.md').read_text()}\n"}


IMPL = """You are adding ONE new feature to the {name} library ({language}).

Feature: {title}
{summary}

Write the complete new module {mod_path}. It must define `{symbol}`, be self-contained
(standard library plus {name}'s own API), follow the library's style (type hints, docstrings)
and reject bad input with clear errors and exact messages. The factory exports it as {name}.{symbol}.
{ex}
{name} API outline:
{outline}

Reply with ONLY the content of {mod_path}."""

TESTS = """Write pytest tests for a new feature of the {name} library.

Feature: {title}
{summary}

The implementation ({mod_path}, used as {name}.{symbol}):
{impl}

Write the complete test file {test_path}. Rules:
- import {name} and use {name}.{symbol}; do not import from the module file directly.
- every expected value must be exactly what THIS implementation returns: trace the code.
- cover normal use, edge cases and every error (pytest.raises with match=).
- 5 to 12 test functions, deterministic, offline, no terminal input.
{ex}
Reply with ONLY the content of the test file."""

FIX_TESTS = """Some tests for {name}.{symbol} fail. The implementation is correct; fix the TESTS.

The implementation ({mod_path}):
{impl}

Current test file {test_path}:
{tests}

Problems:
{problems}

Reply with ONLY the complete corrected test file."""

INSTR = """Write the requirement document for this feature of {name}, as a feature request a
developer receives. They will NOT see the code or tests below, yet their own implementation
must pass these tests.

Feature: {title}
Implementation:
{impl}
Tests:
{tests}

Specify precisely: that it is available as {name}.{symbol}; its signature; behaviour for normal
input and for every edge case the tests check; every exact error message or output the tests
check (quote them). Use markdown headings and bullet lists. Do NOT include code from the
implementation and do not mention test files.
{ex}
Reply with ONLY the markdown document."""


def run(cfg: dict, repo: Path, env: dict, proposal: dict, test_file: str, rounds: int, log,
        problems: list[str] | None = None) -> None:
    """Build the feature in the worktree step by step. problems: validator feedback from a
    previous attempt; then only the tests and the instruction are redone."""
    ex = example(cfg)
    f = {**cfg, **proposal, "mod_path": cfg["new_module"].format(module=proposal["module"]),
         "test_path": f"{cfg['test_dir']}/{test_file}"}
    mod, test = repo / f["mod_path"], repo / f["test_path"]

    def ask(step: str, prompt: str) -> str | None:
        try:
            return unfence(chat(prompt, timeout=900))
        except (TimeoutError, OSError) as e:  # a slow reply is a failed round, not a dead task
            log("local_step", step=step, error=f"model call failed: {e}")
            return None

    if problems is None:  # 1. implementation
        export = repo / cfg["export_file"]
        export.write_text(export.read_text() + cfg["export_line"].format(**f) + "\n")
        prompt = IMPL.format(**f, ex=ex["code"], outline=outline(cfg, repo)[:12000])
        for i in range(rounds + 1):
            if (code := ask("impl", prompt)) is None:
                continue
            mod.parent.mkdir(parents=True, exist_ok=True)
            mod.write_text(code)
            ok, out = sh(cfg["import_check"].format(**f), repo, env)
            log("local_step", step="impl", round=i, ok=ok)
            if ok:
                break
            prompt = IMPL.format(**f, ex="", outline="") + f"\n\nYour previous version:\n{code}\nIt failed:\n{out}\nFix it."
        else:
            return

    impl = mod.read_text() if mod.exists() else ""
    # 2. tests
    if problems is None or not test.exists():
        if (tests := ask("tests", TESTS.format(**f, impl=impl, ex=ex["tests"]))) is None:
            return
        test.write_text(tests)
    issues = problems or []
    for i in range(rounds + 1):
        ok, out = sh(cfg["host_test_cmd"].format(path=f["test_path"]), repo, env)
        log("local_step", step="tests", round=i, ok=ok and not issues)
        if ok and not issues:
            break
        if i == rounds:  # last resort: keep only the tests that pass
            try:
                kept, left = drop_failing(test.read_text(), out)
            except SyntaxError:
                return
            log("local_step", step="drop_failing", tests_left=left)
            if left < MIN_TESTS:
                return
            test.write_text(kept)
            break
        fixed = ask("fix_tests", FIX_TESTS.format(**f, impl=impl, tests=test.read_text(),
                                                  problems="\n".join(issues) + "\n" + out))
        if fixed:
            test.write_text(fixed)
        issues = []

    # 3. requirement document
    for i in range(rounds + 1):
        doc = ask("instruction", INSTR.format(**f, impl=impl, tests=test.read_text(), ex=ex["instruction"]))
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
    print("local_llm selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
