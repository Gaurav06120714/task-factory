# Task Factory: Innodata AI Hackathon, Track 1

Turns a repository into validated Harbor 0.25 feature-development task packages.

## Layout
```
repos/<name>.toml          everything repo-specific (url, base_commit, test_cmd, Dockerfile)
specs/<repo>/<slug>/       one task spec: instruction.md, solution.patch, feature/ tests, meta.toml
factory/build.py           spec -> Harbor package, validated in the task's own Docker image
factory/grade.py           grader shipped inside every task (stdlib only)
tasks/                     generated Harbor task packages
evidence/                  per-task logs, JUnit XML, validation reports
work/                      repo clones (not committed)
```

## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install "harbor==0.25.*" pytest
```

Docker must be running (OrbStack or Docker Desktop).

## Build and validate one task
```bash
.venv/bin/python -m factory.build repos/click.toml specs/click/duration-param-type
.venv/bin/harbor lint tasks/click-duration-param-type
```
The regression list (`pass_to_pass`) is collected inside the task image, not on the host. On macOS, pytest 9.x and a missing `less` gave different results from the Linux image, so a list collected on the host would not match what Harbor grades.

## Harbor validation
```bash
harbor run -p tasks/click-duration-param-type -a nop    -k 1 -o jobs/nop    --no-delete -y   # expect 0.0
harbor run -p tasks/click-duration-param-type -a oracle -k 1 -o jobs/oracle --no-delete -y   # expect 1.0
```

## Grading
- The verifier runs in a **separate** container. The agent's work is passed across only as `git diff`, which `[[verifier.collect]]` saves to `/logs/artifacts/agent.patch`.
- Reward is 0.0 if any `pass_to_pass` test fails. Otherwise it is the share of `fail_to_pass` tests passing.
- Test results are read from JUnit XML. pytest, vitest and ctest can all produce it, so the same grader works for any of the three repos.
