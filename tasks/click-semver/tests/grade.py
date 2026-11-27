"""Task grader. Copied into every task's tests/ folder and run by tests/test.sh.

Stdlib only, so it runs in any task image that has python3.

Reward (Participant Guide):
  any pass_to_pass test not passing -> 0.0
  otherwise                         -> share of fail_to_pass tests passing
"""

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def junit_results(xml_path: Path) -> dict[str, bool]:
    """Map 'classname::name' -> passed, from a JUnit XML file."""
    if not xml_path.exists():
        return {}
    results = {}
    for case in ET.parse(xml_path).iter("testcase"):
        tid = f"{case.get('classname', '')}::{case.get('name', '')}"
        failed = any(case.find(tag) is not None for tag in ("failure", "error"))
        skipped = case.find("skipped") is not None
        results[tid] = not failed and not skipped
    return results


def run_suite(repo: Path, test_cmd: str, junit: Path) -> dict[str, bool]:
    junit.unlink(missing_ok=True)
    cmd = test_cmd.format(junit=junit)
    proc = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, text=True)
    sys.stdout.write(proc.stdout[-4000:])
    sys.stderr.write(proc.stderr[-4000:])
    return junit_results(junit)


def compute_reward(results: dict[str, bool], f2p: list[str], p2p: list[str]) -> float:
    if not all(results.get(t, False) for t in p2p):
        return 0.0
    if not f2p:
        return 0.0
    return sum(results.get(t, False) for t in f2p) / len(f2p)


def install_feature_tests(tests: Path, repo: Path, test_dir: str) -> None:
    src = tests / "feature"
    for f in src.rglob("*"):
        if f.is_file():
            dest = repo / test_dir / f.relative_to(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--tests", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    cfg = json.loads((a.tests / "config.json").read_text())
    f2p = json.loads((a.tests / "fail_to_pass.json").read_text())
    p2p = json.loads((a.tests / "pass_to_pass.json").read_text())

    install_feature_tests(a.tests, a.repo, cfg["test_dir"])
    a.out.mkdir(parents=True, exist_ok=True)
    results = run_suite(a.repo, cfg["test_cmd"], a.out / "junit.xml")
    reward = compute_reward(results, f2p, p2p)

    (a.out / "reward.txt").write_text(f"{reward}\n")
    (a.out / "grade_details.json").write_text(json.dumps({
        "reward": reward,
        "fail_to_pass_passed": [t for t in f2p if results.get(t)],
        "fail_to_pass_failed": [t for t in f2p if not results.get(t)],
        "pass_to_pass_failed": [t for t in p2p if not results.get(t)],
    }, indent=2))
    print(f"reward={reward}")


def _selfcheck() -> None:
    r = {"a::1": True, "a::2": True, "f::1": True, "f::2": False}
    assert compute_reward(r, ["f::1", "f::2"], ["a::1", "a::2"]) == 0.5
    assert compute_reward(r, ["f::1"], ["a::1", "f::2"]) == 0.0   # regression broken
    assert compute_reward(r, ["f::9"], ["a::1"]) == 0.0           # missing test = fail
    assert compute_reward(r, [], ["a::1"]) == 0.0                 # no feature tests is invalid


if __name__ == "__main__":
    if sys.argv[1:] == ["--selfcheck"]:
        _selfcheck()
        print("grade selfcheck ok")
    else:
        main()
