"""Checks the generator's non-AI path: extraction and guardrails.

    .venv/bin/python -m pytest -q -p no:anyio factory/test_generate.py

Simulates an agent's finished working tree from the hand-made duration task.
"""

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from factory import generate


@pytest.fixture(autouse=True)
def _scratch_log(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "LOG", tmp_path / "log.jsonl")

ROOT = generate.ROOT
CFG = tomllib.loads((ROOT / "repos" / "click.toml").read_text())
SPEC = ROOT / "specs" / "click" / "duration-param-type"
PROPOSAL = {"slug": "x", "title": "Duration type", "area": "types",
            "change_kind": "new_public_api", "difficulty": "medium", "tags": ["t"]}


def fake_agent(repo: Path, instruction: str | None = None) -> None:
    subprocess.run(["git", "apply", str(SPEC / "solution.patch")], cwd=repo, check=True)
    shutil.copy(SPEC / "feature" / "test_duration_type.py", repo / "tests" / "test_tf_x.py")
    (repo / "TASK_INSTRUCTION.md").write_text(instruction or (SPEC / "instruction.md").read_text())


def test_extract_roundtrip(tmp_path):
    with generate.worktree(CFG) as repo:
        fake_agent(repo)
        assert generate.extract_spec(CFG, repo, PROPOSAL, "test_tf_x.py", tmp_path / "s") == []
    out = tmp_path / "s"
    assert (out / "solution.patch").read_text().count("+class Duration(") == 1
    assert "tests/" not in (out / "solution.patch").read_text()
    assert (out / "feature" / "test_tf_x.py").exists()
    meta = tomllib.loads((out / "meta.toml").read_text())
    assert meta["area"] == "types" and meta["change_kind"] == "new_public_api"


def test_rejects_edited_existing_test(tmp_path):
    with generate.worktree(CFG) as repo:
        fake_agent(repo)
        with (repo / "tests" / "test_basic.py").open("a") as f:
            f.write("\n# tampered\n")
        problems = generate.extract_spec(CFG, repo, PROPOSAL, "test_tf_x.py", tmp_path / "s")
    assert any("existing test file modified" in p for p in problems)


def test_rejects_leaky_instruction(tmp_path):
    leaky = (SPEC / "instruction.md").read_text() + "\nSee tests in test_tf_x.py.\n"
    with generate.worktree(CFG) as repo:
        fake_agent(repo, leaky)
        problems = generate.extract_spec(CFG, repo, PROPOSAL, "test_tf_x.py", tmp_path / "s")
    assert any("leaks" in p for p in problems)


def test_rejects_changes_outside_source(tmp_path):
    with generate.worktree(CFG) as repo:
        fake_agent(repo)
        (repo / "pyproject.toml").write_text("tampered")
        problems = generate.extract_spec(CFG, repo, PROPOSAL, "test_tf_x.py", tmp_path / "s")
    assert any("outside allowed source paths" in p for p in problems)


def test_proposal_filter():
    existing = [{"slug": "duration-param-type", "area": "types", "change_kind": "new_public_api"}]
    props = [
        {"slug": "a", "title": "t", "area": "types", "change_kind": "new_public_api", "summary": "s"},
        {"slug": "b", "title": "t", "area": "help", "change_kind": "output_format", "summary": "s"},
        {"slug": "c", "title": "t", "area": "help", "change_kind": "output_format", "summary": "s"},
        {"slug": "d", "title": "t", "area": "core", "change_kind": "behaviour_rule", "summary": "s",
         "new_symbols": ["DateTime"]},  # already exists in click
        {"slug": "e", "title": "t", "area": "x", "change_kind": "error_handling", "summary": "s",
         "files": ["src/click/edit.py"]},  # no such file
        {"slug": "f", "title": "t", "area": "click.types", "change_kind": "new_public_api", "summary": "s",
         "files": ["src/click/types.py"]},  # area normalises to "types" -> duplicate
        {"slug": "g", "title": "t", "area": "click.parser", "change_kind": "behaviour_rule", "summary": "s",
         "files": ["src/click/parser.py"]},
        {"slug": "h", "title": "t", "area": "types2", "change_kind": "new_public_api", "summary": "s",
         "module": "types", "symbol": "Thing"},  # local backend: module file already exists
        {"slug": "i", "title": "t", "area": "x y", "change_kind": "new_public_api", "summary": "s",
         "module": "x y", "symbol": "Thing"},  # not an identifier
    ]
    kept = generate.filter_proposals(CFG, props, existing)
    assert [p["slug"] for p in kept] == ["b", "g"]
    assert kept[1]["area"] == "parser"
