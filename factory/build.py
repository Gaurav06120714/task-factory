"""Turn a task spec into a Harbor 0.25 task package, validating it locally on the way.

    python -m factory.build repos/click.toml specs/click/<slug>

A spec folder holds:
    instruction.md     requirement text (the only thing the evaluated AI sees)
    solution.patch     reference implementation, as a git diff against base_commit
    feature/           new test files, laid out relative to the repo's test_dir
    meta.toml          title, area, change_kind, difficulty, tags

Local validation (no Docker) runs the same grade.py the container will run:
    clean base               -> every passing test becomes pass_to_pass
    base + patch + tests     -> new passing tests become fail_to_pass
    nop    (tests, no patch) -> reward must be 0.0
    oracle (tests + patch)   -> reward must be 1.0
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from contextlib import contextmanager
from pathlib import Path

from factory import grade

ROOT = Path(__file__).resolve().parent.parent


def sh(cmd: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, cwd=cwd, env=env, check=True,
                          capture_output=True, text=True)


def clone(cfg: dict) -> Path:
    path = ROOT / "work" / cfg["name"]
    if not path.exists():
        sh(f"git clone -q {cfg['url']} {path}", ROOT)
    return path


@contextmanager
def worktree(cfg: dict):
    """Fresh, detached checkout of base_commit; removed afterwards."""
    src = clone(cfg)
    tmp = Path(tempfile.mkdtemp(prefix=f"tf-{cfg['name']}-"))
    sh(f"git worktree add -q --detach {tmp} {cfg['base_commit']}", src)
    try:
        yield tmp
    finally:
        sh(f"git worktree remove --force {tmp}", src)


def local_env(cfg: dict, repo: Path) -> dict:
    env = dict(os.environ)
    env["PATH"] = f"{Path(sys.executable).parent}:{env['PATH']}"
    for k, v in cfg.get("local_env", {}).items():
        env[k] = str(repo / v)
    return env


def run(cfg: dict, repo: Path, out: Path) -> dict[str, bool]:
    out.mkdir(parents=True, exist_ok=True)
    junit = out / "junit.xml"
    junit.unlink(missing_ok=True)
    proc = subprocess.run(cfg["test_cmd"].format(junit=junit), shell=True, cwd=repo,
                          env=local_env(cfg, repo), capture_output=True, text=True)
    (out / "log.txt").write_text(proc.stdout + proc.stderr)
    return grade.junit_results(junit)


def grade_run(cfg: dict, task: Path, apply_patch: bool, out: Path) -> dict:
    """Exactly what Harbor's nop / oracle runs do, minus Docker."""
    with worktree(cfg) as repo:
        if apply_patch:
            sh(f"git apply {task / 'solution' / 'solution.patch'}", repo)
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(task / "tests" / "grade.py"),
                        "--repo", str(repo), "--tests", str(task / "tests"), "--out", str(out)],
                       cwd=repo, env=local_env(cfg, repo), capture_output=True, text=True)
    return json.loads((out / "grade_details.json").read_text())


TASK_TOML = """schema_version = "1.4"
artifacts = []

[task]
name = "taskfactory/{task_id}"
version = "1.0.0"
description = {title}
authors = []
keywords = {tags}

[metadata]
repo_url = "{url}"
repo_name = "{name}"
base_commit = "{base_commit}"
license = "{license}"
language = "{language}"
area = {area}
change_kind = {change_kind}
difficulty = {difficulty}
category = "software_engineering"
tags = {tags}

[verifier]
timeout_sec = 900.0
# Tests run in a fresh copy of the environment; the agent's work arrives only as a
# git diff, so nothing the agent does to the sandbox can touch the grader.
environment_mode = "separate"

[verifier.env]

[[verifier.collect]]
command = "mkdir -p /logs/artifacts && cd /app/repo && git add -A && git diff --cached --binary HEAD > /logs/artifacts/agent.patch"

[agent]
timeout_sec = 1800.0

[environment]
network_mode = "public"
build_timeout_sec = 900.0
os = "linux"
mcp_servers = []

[environment.env]

[solution.env]
"""

TEST_SH = """#!/bin/bash
# Runs in a fresh verifier container (separate mode). Offline: no network or credentials.
# The agent's changes arrive as /logs/artifacts/agent.patch (written by [[verifier.collect]]).
cd /app/repo
mkdir -p /logs/verifier
PATCH=/logs/artifacts/agent.patch
if [ -s "$PATCH" ] && ! git apply --whitespace=nowarn "$PATCH"; then
  echo "agent patch does not apply cleanly" >&2
  echo 0 > /logs/verifier/reward.txt
  exit 0
fi
python3 /tests/grade.py --repo /app/repo --tests /tests --out /logs/verifier
"""

SOLVE_SH = """#!/bin/bash
set -euo pipefail
cd /app/repo
git apply /solution/solution.patch
"""


def q(s: str) -> str:
    return json.dumps(s)  # TOML basic strings and JSON strings agree for our text


def package(cfg: dict, spec: Path, out_dir: Path, f2p: list[str], p2p: list[str]) -> Path:
    meta = tomllib.loads((spec / "meta.toml").read_text())
    task_id = f"{cfg['name']}-{spec.name}"
    task = out_dir / task_id
    if task.exists():
        shutil.rmtree(task)
    (task / "environment").mkdir(parents=True)
    (task / "solution").mkdir()
    (task / "tests").mkdir()

    shutil.copy(spec / "instruction.md", task / "instruction.md")
    (task / "task.toml").write_text(TASK_TOML.format(
        task_id=task_id, title=q(meta["title"]), tags=json.dumps(meta.get("tags", [])),
        area=q(meta["area"]), change_kind=q(meta["change_kind"]),
        difficulty=q(meta.get("difficulty", "medium")), **cfg))
    (task / "environment" / "Dockerfile").write_text(
        cfg["dockerfile"].format(**cfg).lstrip())
    shutil.copy(spec / "solution.patch", task / "solution" / "solution.patch")
    (task / "solution" / "solve.sh").write_text(SOLVE_SH)
    (task / "tests" / "test.sh").write_text(TEST_SH)
    shutil.copy(Path(grade.__file__), task / "tests" / "grade.py")
    shutil.copytree(spec / "feature", task / "tests" / "feature")
    (task / "tests" / "config.json").write_text(json.dumps(
        {"test_cmd": cfg["test_cmd"], "test_dir": cfg["test_dir"]}, indent=2))
    (task / "tests" / "fail_to_pass.json").write_text(json.dumps(f2p, indent=2))
    (task / "tests" / "pass_to_pass.json").write_text(json.dumps(p2p, indent=2))
    for s in ("solution/solve.sh", "tests/test.sh"):
        (task / s).chmod(0o755)
    return task


def build(repo_toml: Path, spec: Path) -> dict:
    cfg = tomllib.loads(repo_toml.read_text())
    spec = spec.resolve()
    evidence = ROOT / "evidence" / f"{cfg['name']}-{spec.name}"
    if evidence.exists():
        shutil.rmtree(evidence)

    # 1. Clean base: what passes today is the regression set.
    with worktree(cfg) as repo:
        base = run(cfg, repo, evidence / "base")
    p2p = sorted(t for t, ok in base.items() if ok)
    if not p2p:
        raise SystemExit("base run produced no passing tests; check test_cmd")

    # 2. Base + patch + feature tests: new tests that pass are the feature set.
    with worktree(cfg) as repo:
        sh(f"git apply {spec / 'solution.patch'}", repo)
        grade.install_feature_tests(spec, repo, cfg["test_dir"])
        oracle_raw = run(cfg, repo, evidence / "oracle_raw")
    new = sorted(set(oracle_raw) - set(base))
    f2p = [t for t in new if oracle_raw[t]]
    problems = [f"new test not passing with reference patch: {t}" for t in new if not oracle_raw[t]]
    problems += [f"regression broken by patch: {t}" for t in p2p if not oracle_raw.get(t)]
    if not f2p:
        problems.append("no fail_to_pass tests found")

    task = package(cfg, spec, ROOT / "tasks", f2p, p2p)

    # 3. The two checks Harbor will run, done locally with the packaged grader.
    nop = grade_run(cfg, task, apply_patch=False, out=evidence / "nop")
    oracle = grade_run(cfg, task, apply_patch=True, out=evidence / "oracle")
    if nop["reward"] != 0.0 or nop["fail_to_pass_passed"]:
        problems.append(f"nop reward {nop['reward']} (want 0.0); passing: {nop['fail_to_pass_passed']}")
    if nop["pass_to_pass_failed"]:
        problems.append(f"nop broke regressions: {nop['pass_to_pass_failed'][:5]}")
    if oracle["reward"] != 1.0:
        problems.append(f"oracle reward {oracle['reward']} (want 1.0)")

    report = {"task": task.name, "base_commit": cfg["base_commit"],
              "fail_to_pass": len(f2p), "pass_to_pass": len(p2p),
              "nop_reward": nop["reward"], "oracle_reward": oracle["reward"],
              "valid": not problems, "problems": problems}
    (evidence / "local_validation.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(build(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
