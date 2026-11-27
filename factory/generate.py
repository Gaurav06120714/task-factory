"""AI task generation: propose -> implement -> extract spec -> validate in Docker -> retry.

    python -m factory.generate repos/click.toml --count 4

The model only drafts. Nothing becomes a task until factory.build has shown, in the
task's own Docker image, that unchanged code scores 0.0 and the reference patch 1.0.

Guardrails (each rejection is logged to evidence/generation_log.jsonl):
  proposals  distinct (area, change_kind) from every existing task and each other
             new public names must not already exist in the repo's upstream main
  extraction feature tests must be NEW files; existing tests may not be edited
             the patch may only touch the repo's declared source paths
             the instruction must be self-contained and must not leak the solution
  validation nop 0.0 / oracle 1.0 / no regressions, with up to N repair rounds
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from contextlib import contextmanager
from pathlib import Path

from factory import build, local_llm

ROOT = build.ROOT
# "ollama" (free, local; default) or "claude" (headless Claude Code CLI).
BACKEND = os.environ.get("TF_BACKEND", "ollama")
CLAUDE = os.environ.get("TF_CLAUDE", "claude")
MODEL = os.environ.get("TF_MODEL", "opus") if BACKEND == "claude" else local_llm.MODEL
LOG = ROOT / "evidence" / "generation_log.jsonl"


def log(event: str, **data) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **data}) + "\n")
    print(f"[{event}] " + json.dumps(data)[:300], flush=True)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def clone(cfg: dict) -> Path:
    path = ROOT / "work" / cfg["name"]
    if not path.exists():
        subprocess.run(["git", "clone", "-q", cfg["url"], str(path)], check=True)
    return path


@contextmanager
def worktree(cfg: dict):
    src = clone(cfg)
    tmp = Path(tempfile.mkdtemp(prefix=f"tf-{cfg['name']}-"))
    git("worktree", "prune", cwd=src)  # drop stale entries left by a crashed run
    try:
        git("worktree", "add", "-q", "--detach", str(tmp), cfg["base_commit"], cwd=src)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    try:
        yield tmp
    finally:
        git("worktree", "remove", "--force", str(tmp), cwd=src)


# ---------------------------------------------------------------- model calls

def claude(prompt: str, cwd: Path, tools: list[str], env: dict | None = None) -> dict:
    """One headless Claude Code run. Edits are auto-accepted inside cwd only;
    Bash is limited to the patterns in `tools`."""
    cmd = [CLAUDE, "-p", prompt, "--model", MODEL, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--allowedTools", ",".join(tools)]
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=3600)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude returned non-JSON: {proc.stdout[-500:]} {proc.stderr[-500:]}")
    if out.get("is_error"):
        raise RuntimeError(f"claude error: {out.get('result')}")
    log("claude_call", cwd=str(cwd), turns=out.get("num_turns"),
        cost_usd=out.get("total_cost_usd"), seconds=round(out.get("duration_ms", 0) / 1000))
    return out


def agent_env(cfg: dict, repo: Path) -> dict:
    env = dict(os.environ)
    env["PATH"] = f"{Path(sys.executable).parent}:{env['PATH']}"
    for k, v in cfg.get("agent_env", {}).items():
        env[k] = str(repo / v)
    return env


# ---------------------------------------------------------------- proposing

def existing_tasks(cfg: dict) -> list[dict]:
    out = []
    for meta in sorted((ROOT / "specs" / cfg["name"]).glob("*/meta.toml")):
        m = tomllib.loads(meta.read_text())
        out.append({"slug": meta.parent.name, **m})
    return out


PROPOSE = """You are designing realistic feature-development tasks for evaluating AI coding agents.
Repository: {name} ({language}), checked out at release commit {base_commit}.

Study the code under {source_paths} and the tests under {test_dir}/, then propose {n} NEW features.

Every proposal must:
- be a new feature or a change to existing behaviour that a maintainer could plausibly accept. NOT a bug fix, refactor, docs-only change or performance tweak.
- be implementable in roughly 30-200 lines plus tests, inside this repository only, without new dependencies.
- be fully testable offline and deterministically (no network, no real credentials, no timing races).
- not create or exploit security vulnerabilities.
- not already exist in this repository or in its upstream main branch.
- differ in BEHAVIOUR from the others and from the existing tasks below. Renaming, rewording or changing constants does not count as different. Use a different `area` and/or `change_kind` from every existing task.

Allowed change_kind values: new_public_api, new_option_or_parameter, behaviour_rule, output_format, error_handling, feature_interaction.

Existing tasks (do not repeat their area+change_kind or their idea):
{existing}

Reply with ONLY a JSON array, no prose. Each element:
{{"slug": "kebab-case-id", "title": "...", "area": "short module/subsystem name", "change_kind": "...",
  "summary": "2-4 sentences of the behaviour to add", "new_symbols": ["public names this adds, e.g. Duration"],
  "files": ["existing source files to change, e.g. src/pkg/module.py"],
  "difficulty": "easy|medium|hard", "tags": ["..."], "why_realistic": "one sentence"}}
"""


PROPOSE_LOCAL = """You are designing feature tasks for evaluating AI coding agents on the {name} library ({language}).

Propose exactly one feature for EACH theme below, in order. Each is ONE new public class or
function in its own new module, exported as {name}.<Symbol>. Make each concrete: exact inputs,
outputs, accepted formats, edge cases and error messages.
Themes:
{themes}

Rules: genuinely useful to people writing command-line apps with {name}; not already in {name}
(its public API is below); 40-120 lines with real logic (validation, parsing rules, edge cases);
standard library only; deterministic and testable offline with no terminal input; every idea
different in behaviour. NOT trivial string helpers (case conversion, reversing, padding).
Every proposal MUST include both "module" and "symbol".
Already taken:
{existing}

Return {{"proposals": [{{"slug": "kebab-case", "title": "...", "module": "snake_case_module",
"symbol": "PublicName", "summary": "2-4 sentences: inputs, outputs, error cases",
"difficulty": "easy|medium|hard", "tags": ["..."]}}]}}

Public API of {name}:
{api}"""


def parse_json_array(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end < start:
            raise ValueError("no JSON array in model output")
        data = json.loads(text[start:end + 1])
    if isinstance(data, dict):  # JSON mode returns an object: take its list value
        data = next((v for v in data.values() if isinstance(v, list)), [data])
    return [p for p in data if isinstance(p, dict)]


def upstream_has(cfg: dict, symbol: str) -> bool:
    """True if the identifier already exists on the repo's upstream main."""
    src = clone(cfg)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=src, check=False)
    for ref in ("origin/main", cfg["base_commit"]):
        res = subprocess.run(["git", "grep", "-q", "-w", "-F", symbol, ref, "--", *cfg["source_paths"]],
                             cwd=src, capture_output=True)
        if res.returncode == 0:
            return True
    return False


def git_has(repo: Path, ref: str, path: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{ref}:{path}"], cwd=repo,
                          capture_output=True).returncode == 0


def filter_proposals(cfg: dict, proposals: list[dict], existing: list[dict]) -> list[dict]:
    seen = {(e["area"], e["change_kind"]) for e in existing}
    slugs = {e["slug"] for e in existing}
    kept = []
    base = clone(cfg)
    for p in proposals:
        files = [f for f in p.get("files", []) if isinstance(f, str)]
        if files and "area" in p:  # canonical area = module the feature lives in
            p["area"] = Path(files[0]).stem
        key = (p.get("area"), p.get("change_kind"))
        reason = None
        missing = [f for f in files if not git_has(base, cfg["base_commit"], f)]
        if not all(p.get(k) for k in ("slug", "title", "area", "change_kind", "summary")):
            reason = "missing fields"
        elif missing:
            reason = f"names files that do not exist: {missing}"
        elif "module" in p and not (str(p["module"]).isidentifier() and str(p.get("symbol")).isidentifier()):
            reason = "module/symbol is not a valid identifier"
        elif "module" in p and git_has(base, cfg["base_commit"], cfg["new_module"].format(module=p["module"])):
            reason = "module already exists"
        elif p["slug"] in slugs:
            reason = "duplicate slug"
        elif key in seen:
            reason = f"area+change_kind {key} already covered"
        else:
            clash = [s for s in p.get("new_symbols", []) if len(s) > 3 and upstream_has(cfg, s)]
            if clash:
                reason = f"already exists upstream: {clash}"
        if reason:
            log("proposal_rejected", slug=p.get("slug"), reason=reason)
            continue
        seen.add(key)
        slugs.add(p["slug"])
        kept.append(p)
    return kept


def propose(cfg: dict, n: int) -> list[dict]:
    existing = existing_tasks(cfg)
    listing = "\n".join(f"- {e['slug']}: {e['title']} [area={e['area']}, change_kind={e['change_kind']}]"
                        for e in existing) or "- (none)"
    prompt = PROPOSE.format(n=n * 2, existing=listing, **{**cfg, "source_paths": ", ".join(cfg["source_paths"])})
    with worktree(cfg) as repo:
        if BACKEND == "claude":
            text = claude(prompt, repo, ["Read", "Glob", "Grep"])["result"]
        else:  # small local model: one new exported module per feature (see local_llm)
            api = "\n".join(l for l in (repo / cfg["export_file"]).read_text().splitlines() if "import" in l)
            text = local_llm.chat(PROPOSE_LOCAL.format(**{**cfg, "n": n + 2, "existing": listing, "api": api,
                                  "themes": "\n".join(f"- {t}" for t in cfg.get("local_themes", []))}),
                                  json_mode=True)
    proposals = parse_json_array(text)
    if BACKEND != "claude":
        for p in proposals:
            if not str(p.get("module", "")).isidentifier():  # 7B often drops or hyphenates it
                p["module"] = str(p.get("slug", "")).replace("-", "_")
            p.update(area=p.get("module"), change_kind="new_public_api",
                     new_symbols=[p.get("symbol")], files=[])
    log("proposed", count=len(proposals), slugs=[p.get("slug") for p in proposals])
    return filter_proposals(cfg, proposals, existing)[:n]


# ---------------------------------------------------------------- implementing

IMPLEMENT = """Implement this feature in the repository in the current directory, as a careful maintainer would.

Feature: {title}
{summary}

Do exactly this:
1. Implement the feature under {source_paths}. Follow the project's existing style, typing and docstring conventions, and export any new public names the way the project already does. Do not add dependencies.
2. Add tests in ONE NEW file: {test_dir}/{test_file}. Do NOT edit or delete any existing test file. The tests must:
   - fail on the original code and pass with your implementation;
   - cover the main behaviour, edge cases and every error path with its exact message;
   - be deterministic and offline, and use only what the project's tests already use (e.g. its test runner helpers).
3. Write TASK_INSTRUCTION.md in the repository root: the requirement document a developer receives, who will NOT see your code or tests. It must specify, precisely enough that an independent implementation passes your tests:
   - the public API (names, signatures, where it is exported from);
   - the behaviour, including edge cases;
   - every exact user-facing message your tests check.
   Write it as a feature request, not a walkthrough: no code from your implementation, no file names of your tests, no step-by-step hints.
4. {test_hint}. Run your new test file and the full existing suite; both must pass before you finish.
Do not create any other files."""

REPAIR = """The task you prepared in this repository failed automated validation:
{problems}

Fix the implementation, the tests in {test_dir}/{test_file} and/or TASK_INSTRUCTION.md so that:
the new tests fail on the original code, pass with your implementation, and no existing test breaks.
Do not edit existing test files. {test_hint}."""


def extract_spec(cfg: dict, repo: Path, proposal: dict, test_file: str, spec_dir: Path) -> list[str]:
    """Turn the agent's working tree into a spec folder. Returns guardrail problems."""
    problems = []
    git("add", "-A", cwd=repo)
    changed = [l.split("\t") for l in git("diff", "--cached", "--name-status", "HEAD", cwd=repo).splitlines()]
    test_dir = cfg["test_dir"].rstrip("/") + "/"
    new_tests, src_changes = [], []
    for status, *paths in changed:
        path = paths[-1]
        if path == "TASK_INSTRUCTION.md":
            continue
        if path.startswith(test_dir):
            if status == "A":
                new_tests.append(path)
            else:
                problems.append(f"existing test file modified ({status}): {path}")
        elif any(path == p or path.startswith(p.rstrip("/") + "/") for p in cfg["source_paths"]):
            src_changes.append(path)
        else:
            problems.append(f"change outside allowed source paths: {path}")
    if not new_tests:
        problems.append("no new test file")
    if not src_changes:
        problems.append("no source changes")

    instr_path = repo / "TASK_INSTRUCTION.md"
    instruction = instr_path.read_text() if instr_path.exists() else ""
    if len(instruction) < 300:
        problems.append("TASK_INSTRUCTION.md missing or too short")
    if "```diff" in instruction or any(Path(t).name in instruction for t in new_tests):
        problems.append("instruction leaks the solution or test file names")
    if problems:
        return problems

    if spec_dir.exists():
        shutil.rmtree(spec_dir)
    (spec_dir / "feature").mkdir(parents=True)
    patch = git("diff", "--cached", "--binary", "HEAD", "--", *src_changes, cwd=repo)
    (spec_dir / "solution.patch").write_text(patch)
    for t in new_tests:
        dest = spec_dir / "feature" / Path(t).relative_to(cfg["test_dir"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(repo / t, dest)
    (spec_dir / "instruction.md").write_text(instruction)
    meta = {k: proposal.get(k) for k in ("title", "area", "change_kind", "difficulty")}
    (spec_dir / "meta.toml").write_text(
        "".join(f"{k} = {json.dumps(v or 'medium')}\n" for k, v in meta.items())
        + f"tags = {json.dumps(proposal.get('tags', []))}\n"
        + f"generated_by = {json.dumps(f"{BACKEND}/{MODEL}")}\n")
    git("reset", "-q", cwd=repo)  # unstage; keep the working tree for repair rounds
    return []


def generate_one(repo_toml: Path, cfg: dict, proposal: dict, repairs: int) -> dict:
    slug = proposal["slug"]
    test_file = f"test_tf_{slug.replace('-', '_')}.py"
    spec_dir = ROOT / "specs" / cfg["name"] / slug
    hint = cfg["agent_test_hint"] if BACKEND == "claude" else "The factory runs the tests for you and reports failures"
    fmt = {**cfg, **proposal, "test_file": test_file, "test_hint": hint,
           "source_paths": ", ".join(cfg["source_paths"])}
    tools = ["Read", "Edit", "Write", "Glob", "Grep"] + [f"Bash({b})" for b in cfg["agent_bash"]]

    def ask(prompt: str, problems: list[str] | None = None) -> None:
        if BACKEND == "claude":
            claude(prompt, repo, tools, env)
        else:
            local_llm.run(cfg, repo, env, proposal, test_file, repairs, log, problems)

    with worktree(cfg) as repo:
        env = agent_env(cfg, repo)
        ask(IMPLEMENT.format(**fmt))
        for attempt in range(repairs + 1):
            problems = extract_spec(cfg, repo, proposal, test_file, spec_dir)
            report = None
            if not problems:
                report = build.build(repo_toml, spec_dir)
                problems = report["problems"]
            log("attempt", slug=slug, attempt=attempt, valid=not problems, problems=problems[:8])
            if not problems:
                return {"slug": slug, "valid": True, "attempts": attempt + 1, **report}
            if attempt < repairs:
                ask(REPAIR.format(problems="\n".join(f"- {p}" for p in problems[:20]), **fmt), problems[:20])

    # Keep rejected work as evidence of what the guardrails caught.
    if spec_dir.exists():
        dest = ROOT / "specs_rejected" / cfg["name"] / slug
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(spec_dir), dest)
        task = ROOT / "tasks" / f"{cfg['name']}-{slug}"
        shutil.rmtree(task, ignore_errors=True)
    return {"slug": slug, "valid": False, "problems": problems}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_toml", type=Path)
    ap.add_argument("--count", type=int, default=4, help="valid tasks wanted")
    ap.add_argument("--repairs", type=int, default=2, help="repair rounds per task")
    a = ap.parse_args()
    cfg = tomllib.loads(a.repo_toml.read_text())

    results = []
    for p in propose(cfg, a.count + 2):  # a little headroom for rejections
        if sum(r["valid"] for r in results) >= a.count:
            break
        log("generating", slug=p["slug"], area=p["area"], change_kind=p["change_kind"])
        try:
            results.append(generate_one(a.repo_toml, cfg, p, a.repairs))
        except Exception as e:  # one bad task must not stop the factory
            log("error", slug=p["slug"], error=str(e)[:500])
            results.append({"slug": p["slug"], "valid": False, "problems": [str(e)[:500]]})
        log("result", **{k: results[-1].get(k) for k in ("slug", "valid", "attempts", "problems")})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
