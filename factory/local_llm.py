"""Free, local backend for the generator: Ollama + an edit protocol the factory applies.

A small local model cannot browse files or run tools, so the factory does that for it:
it shows the model the source files, asks for exact SEARCH/REPLACE edits plus new files,
applies them to the worktree, runs the tests and feeds failures back.

Env: TF_OLLAMA_MODEL (default qwen2.5-coder:7b), TF_OLLAMA_URL, TF_OLLAMA_CTX.
"""

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


def file_block(repo: Path, rel: str) -> str:
    text = (repo / rel).read_text(errors="ignore")[:MAX_FILE_CHARS]
    return f"=== FILE {rel}\n{text}\n=== END FILE"


# ---------------------------------------------------------------- edit protocol

PROTOCOL = """Reply ONLY with blocks in this exact format, nothing else:

=== EDIT <path>
<<<<<<< SEARCH
<lines copied EXACTLY from the current file, enough to be unique>
=======
<the replacement lines>
>>>>>>> REPLACE
=== END

=== NEW <path>
<full content of a new file>
=== END

Use as many EDIT blocks as needed (one SEARCH/REPLACE per block). To insert code, SEARCH
for a nearby existing line and REPLACE with that line plus the new code."""

BLOCK_RE = re.compile(r"^=== (EDIT|NEW) (\S+)\n(.*?)^=== END\s*$", re.S | re.M)
SR_RE = re.compile(r"<<<<<<< SEARCH\n(.*?)\n?=======\n(.*?)\n?>>>>>>> REPLACE", re.S)


FENCE_RE = re.compile(r"^\s*```[\w+-]*\n(.*?)\n?```\s*$", re.S)


def unfence(body: str) -> str:
    """Small models wrap file bodies in markdown fences; strip them."""
    m = FENCE_RE.match(body)
    body = m.group(1) if m else body
    return re.sub(r"\n```\s*$", "", body)


def parse_blocks(text: str) -> list[tuple[str, str, str]]:
    return [(kind, path, unfence(body) if kind == "NEW" else body)
            for kind, path, body in BLOCK_RE.findall(text)]


def _replace_loose(content: str, search: str, replace: str) -> str | None:
    """Exact match first; then match ignoring trailing whitespace on each line."""
    if search and content.count(search) == 1:
        return content.replace(search, replace, 1)
    lines, want = content.splitlines(keepends=True), [l.rstrip() for l in search.splitlines()]
    n = len(want)
    hits = [i for i in range(len(lines) - n + 1)
            if [l.rstrip() for l in lines[i:i + n]] == want]
    if n and len(hits) == 1:
        i = hits[0]
        return "".join(lines[:i]) + replace + ("\n" if not replace.endswith("\n") else "") + "".join(lines[i + n:])
    return None


def apply_blocks(repo: Path, blocks: list[tuple[str, str, str]]) -> list[str]:
    """Apply edits in place. Returns a list of problems (edits that could not be applied)."""
    problems = []
    root = repo.resolve()
    for kind, rel, body in blocks:
        path = (repo / rel).resolve()
        if root not in path.parents:
            problems.append(f"{rel}: path outside the repository")
            continue
        if kind == "NEW":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body if body.endswith("\n") else body + "\n")
            continue
        if not path.exists():
            problems.append(f"{rel}: file does not exist (use NEW for new files)")
            continue
        pairs = SR_RE.findall(body)
        if not pairs:
            problems.append(f"{rel}: EDIT block without SEARCH/REPLACE")
        content = path.read_text()
        for search, replace in pairs:
            new = _replace_loose(content, search, replace)
            if new is None:
                problems.append(f"{rel}: SEARCH text not found exactly once:\n{search[:300]}")
            else:
                content = new
        path.write_text(content)
    return problems


# ---------------------------------------------------------------- loop

def host_tests(cfg: dict, repo: Path, env: dict, path: str) -> tuple[bool, str]:
    cmd = cfg["host_test_cmd"].format(path=path)
    try:  # stdin closed + timeout: a test waiting for terminal input fails fast instead of hanging
        p = subprocess.run(cmd, shell=True, cwd=repo, env=env, capture_output=True, text=True,
                           timeout=180, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "tests timed out after 180s (a test is probably waiting for input or looping)"
    return p.returncode == 0, (p.stdout + p.stderr)[-4000:]


def touched_files(repo: Path) -> list[str]:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    names = subprocess.run(["git", "diff", "--cached", "--name-only", "HEAD"], cwd=repo,
                           check=True, capture_output=True, text=True).stdout.split()
    subprocess.run(["git", "reset", "-q"], cwd=repo, check=True)
    return names


def worked_example(cfg: dict) -> str:
    """One validated task from this repo, shown to the model as the quality bar."""
    from factory.build import ROOT
    specs = sorted((ROOT / "specs" / cfg["name"]).glob("*/solution.patch"))
    if not specs:
        return ""
    spec = specs[0].parent
    tests = "\n".join(f.read_text() for f in sorted((spec / "feature").rglob("*.py")))
    return ("Here is an EXAMPLE of a finished, validated task for this repository. Match its quality: "
            "a small, self-contained feature; precise requirement text with exact messages; tests that "
            "use the project's test helpers and check exact output.\n"
            f"--- example TASK_INSTRUCTION.md\n{(spec / 'instruction.md').read_text()}\n"
            f"--- example source change (git diff)\n{(spec / 'solution.patch').read_text()}\n"
            f"--- example test file\n{tests}\n--- end of example\n\n")


def run(cfg: dict, repo: Path, env: dict, task_prompt: str, test_file: str,
        files: list[str], rounds: int, log) -> None:
    """Ask for edits, apply, test on host; repair until tests pass or rounds run out."""
    test_path = f"{cfg['test_dir']}/{test_file}"
    files = sorted(f for f in set(files) | set(touched_files(repo)) if (repo / f).is_file())
    prompt = (f"{worked_example(cfg)}{task_prompt}\n\nRepository outline:\n{outline(cfg, repo)}\n\n"
              + "\n\n".join(file_block(repo, f) for f in files) + f"\n\n{PROTOCOL}")
    for i in range(rounds + 1):
        try:
            reply = chat(prompt, timeout=900)
        except (TimeoutError, OSError) as e:  # a slow reply is a failed round, not a dead task
            log("local_round", round=i, error=f"model call failed: {e}")
            continue
        blocks = parse_blocks(reply)
        problems = apply_blocks(repo, blocks) if blocks else ["reply contained no EDIT/NEW blocks"]
        ok_new, out_new = host_tests(cfg, repo, env, test_path) if (repo / test_path).exists() else (False, "test file missing")
        ok_all, out_all = host_tests(cfg, repo, env, cfg["test_dir"]) if ok_new else (False, "")
        log("local_round", round=i, blocks=len(blocks), edit_problems=len(problems),
            new_tests_pass=ok_new, suite_pass=ok_all)
        if not problems and ok_new and ok_all and (repo / "TASK_INSTRUCTION.md").exists():
            return
        current = sorted(set(files) | {f for f in touched_files(repo) if (repo / f).is_file()})
        prompt = (f"{task_prompt}\n\nYour previous edits were applied where possible. Remaining problems:\n"
                  + "\n".join(f"- {p}" for p in problems)
                  + (f"\n\nTest output:\n{out_all or out_new}" if not (ok_new and ok_all) else "")
                  + ("\n- TASK_INSTRUCTION.md is missing" if not (repo / "TASK_INSTRUCTION.md").exists() else "")
                  + "\n\nCurrent files:\n" + "\n\n".join(file_block(repo, f) for f in current)
                  + f"\n\nFix everything. {PROTOCOL}")


def _selfcheck() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d)
        (repo / "a.py").write_text("def f():\n    return 1   \n\n\ndef g():\n    return 2\n")
        reply = ("=== EDIT a.py\n<<<<<<< SEARCH\ndef f():\n    return 1\n=======\ndef f():\n    return 10\n"
                 ">>>>>>> REPLACE\n=== END\n\n=== NEW tests/test_a.py\nassert True\n=== END\n"
                 "=== EDIT a.py\n<<<<<<< SEARCH\nnope\n=======\nx\n>>>>>>> REPLACE\n=== END\n"
                 "=== NEW ../escape.py\nx\n=== END\n")
        blocks = parse_blocks(reply)
        assert [b[0] for b in blocks] == ["EDIT", "NEW", "EDIT", "NEW"]
        problems = apply_blocks(repo, blocks)
        assert "return 10" in (repo / "a.py").read_text()           # loose whitespace match
        assert "return 2" in (repo / "a.py").read_text()            # rest untouched
        assert (repo / "tests" / "test_a.py").read_text() == "assert True\n"
        assert len(problems) == 2 and "not found" in problems[0] and "outside" in problems[1]
        assert not (repo.parent / "escape.py").exists()
        fenced = parse_blocks("=== NEW t.py\n```python\nx = 1\n```\n=== END\n")
        assert fenced[0][2] == "x = 1", fenced              # markdown fences stripped
    print("local_llm selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
