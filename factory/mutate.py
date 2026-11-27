"""Mutation testing: prove a task's feature tests catch broken implementations.

Applies the spec's reference patch, then mutates ONLY the lines that patch added (one small
change per mutant: flipped comparison, swapped operator, off-by-one constant, and/or swap,
dropped `not`, `return None`). A mutant is "killed" when the feature tests fail on it.

    python -m factory.mutate repos/click.toml specs/click/byte-size
Writes evidence/<repo>-<slug>/mutation.json. Python repos only (uses the ast module).
"""
from __future__ import annotations

import ast
import copy
import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

from factory.generate import ROOT, agent_env, git, worktree
from factory.local_llm import sh

SWAP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
        ast.GtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
        ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
        ast.FloorDiv: ast.Mult, ast.Mod: ast.FloorDiv, ast.Pow: ast.Mult, ast.And: ast.Or, ast.Or: ast.And}
MAX_MUTANTS = 40


class Mutator(ast.NodeTransformer):
    """Visits eligible nodes on `lines` in a fixed order; mutates the `target`-th one (or just counts)."""

    def __init__(self, lines: set[int], target: int = -1):
        self.lines, self.target, self.count, self.desc = lines, target, 0, None

    def _hit(self, node, desc: str) -> bool:
        if getattr(node, "lineno", None) not in self.lines:
            return False
        hit = self.count == self.target
        self.count += 1
        if hit:
            self.desc = f"line {node.lineno}: {desc}"
        return hit

    def visit_Compare(self, node):
        self.generic_visit(node)
        if type(node.ops[0]) in SWAP and self._hit(node, f"{type(node.ops[0]).__name__} -> {SWAP[type(node.ops[0])].__name__}"):
            node.ops[0] = SWAP[type(node.ops[0])]()
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in SWAP and self._hit(node, f"{type(node.op).__name__} -> {SWAP[type(node.op)].__name__}"):
            node.op = SWAP[type(node.op)]()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self._hit(node, f"{type(node.op).__name__} -> {SWAP[type(node.op)].__name__}"):
            node.op = SWAP[type(node.op)]()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit(node, "drop `not`"):
            return node.operand
        return node

    def visit_Constant(self, node):
        if type(node.value) is int and self._hit(node, f"{node.value} -> {node.value + 1}"):
            return ast.copy_location(ast.Constant(node.value + 1), node)
        return node

    def visit_Return(self, node):
        self.generic_visit(node)
        if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None) \
                and self._hit(node, "return None"):
            node.value = None
        return node


def added_lines(patch: str) -> dict[str, set[int]]:
    """{path: line numbers added by the patch, in the new file}, .py files only."""
    out, path, n = {}, None, 0
    for line in patch.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") and line.endswith(".py") else None
        elif m := re.match(r"@@ -\S+ \+(\d+)", line):
            n = int(m[1])
        elif path and not line.startswith("---"):
            if line.startswith("+"):
                out.setdefault(path, set()).add(n)
            if not line.startswith("-"):
                n += 1
    return out


def mutate(repo_toml: Path, spec: Path) -> dict:
    cfg = tomllib.loads(repo_toml.read_text())
    patch = (spec / "solution.patch").read_text()
    with worktree(cfg) as repo:
        (repo / "solution.patch").write_text(patch)
        git("apply", "solution.patch", cwd=repo)
        tests = []
        for f in (spec / "feature").rglob("*.py"):
            dest = repo / cfg["test_dir"] / f.relative_to(spec / "feature")
            shutil.copy(f, dest)
            tests.append(str(dest.relative_to(repo)))
        env, cmd = agent_env(cfg, repo), cfg["host_test_cmd"].format(path=" ".join(tests))
        ok, out = sh(cmd, repo, env)
        if not ok:
            raise SystemExit(f"feature tests fail on the reference solution:\n{out}")
        results = []
        for path, lines in added_lines(patch).items():
            src = (repo / path).read_text()
            tree = ast.parse(src)
            counter = Mutator(lines)
            counter.visit(copy.deepcopy(tree))
            for i in range(counter.count):
                m = Mutator(lines, i)
                mutated = ast.unparse(ast.fix_missing_locations(m.visit(copy.deepcopy(tree))))
                (repo / path).write_text(mutated)
                ok, out = sh(cmd, repo, env)
                results.append({"file": path, "mutation": m.desc, "killed": not ok})
                print(f"{'killed  ' if not ok else 'SURVIVED'} {path} {m.desc}", flush=True)
                if len(results) >= MAX_MUTANTS:  # ponytail: cap keeps a run under ~10 min; sample if a patch is huge
                    break
            (repo / path).write_text(src)
    killed = sum(r["killed"] for r in results)
    report = {"spec": spec.name, "mutants": len(results), "killed": killed,
              "score": round(killed / len(results), 3) if results else None,
              "survivors": [r for r in results if not r["killed"]], "all": results}
    out_dir = ROOT / "evidence" / f"{cfg['name']}-{spec.name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mutation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{spec.name}: {killed}/{len(results)} mutants killed")
    return report


def _selfcheck() -> None:
    p = "+++ b/src/x.py\n@@ -1,2 +1,3 @@\n a = 1\n+b = 2\n c = 3\n"
    assert added_lines(p) == {"src/x.py": {2}}
    tree = ast.parse("a = 1\nb = x < 2 and not y\n")
    count = Mutator({2})
    count.visit(copy.deepcopy(tree))
    assert count.count == 4  # Lt, 2, And, not
    got = {ast.unparse(Mutator({2}, i).visit(copy.deepcopy(tree))).splitlines()[1] for i in range(4)}
    assert got == {"b = x < 3 and (not y)", "b = x <= 2 and (not y)", "b = x < 2 or not y", "b = x < 2 and y"}, got


if __name__ == "__main__":
    if sys.argv[1:] == ["--selfcheck"]:
        _selfcheck()
        print("ok")
    else:
        mutate(Path(sys.argv[1]), Path(sys.argv[2]))
