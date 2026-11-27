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
If the checkout is in an iCloud-synced folder (e.g. a synced Desktop), keep `.venv` and `work/` outside it and symlink them in. When disk space is low, macOS offloads their files to iCloud, and every test run then waits for them to download again.

## Build and validate one task
```bash
.venv/bin/python -m factory.build repos/click.toml specs/click/duration-param-type
.venv/bin/harbor lint tasks/click-duration-param-type
```
The regression list (`pass_to_pass`) is collected inside the task image, not on the host. On macOS, pytest 9.x and a missing `less` gave different results from the Linux image, so a list collected on the host would not match what Harbor grades.

## Generate tasks with AI
```bash
.venv/bin/python -m factory.generate repos/click.toml --count 4
```
The default backend is free and local: Ollama with `qwen2.5-coder:7b` (`TF_OLLAMA_MODEL`). A 7B model can't edit existing code reliably, so `factory/local_llm.py` drives it in small steps: (1) one new module, which the factory exports; (2) tests, run on the host, with failures sent back for repair and tests that still fail dropped; (3) the requirement document, written from the code and tests. With `TF_BACKEND=claude`, headless Claude Code (`claude -p`, model `TF_MODEL`, default `opus`) instead proposes features, then implements each one in a throwaway git worktree: the source change, a new test file and `TASK_INSTRUCTION.md`. Each draft has to pass these guardrails before it becomes a task:

| Stage | Guardrail |
|---|---|
| Proposal | its (area, change_kind) differs from every existing task; any new public names must not already exist upstream (`origin/main`) |
| Extraction | tests must be new files (no edits to existing tests); the patch may only touch `source_paths`; the instruction must not leak code or test file names |
| Validation | `factory.build` in Docker: nop 0.0, oracle 1.0, no regressions. On failure the agent gets the problems back, for up to `--repairs` rounds |

Every decision is logged to `evidence/generation_log.jsonl`. Failed drafts are moved to `specs_rejected/`.
Self-check for the non-AI path: `.venv/bin/python -m pytest -q -p no:anyio factory/test_generate.py`.

## Harbor validation
```bash
harbor run -p tasks/click-duration-param-type -a nop    -k 1 -o jobs/nop    --no-delete -y   # expect 0.0
harbor run -p tasks/click-duration-param-type -a oracle -k 1 -o jobs/oracle --no-delete -y   # expect 1.0
```

## Grading
- The verifier runs in a **separate** container. The agent's work is passed across only as `git diff`, which `[[verifier.collect]]` saves to `/logs/artifacts/agent.patch`.
- Reward is 0.0 if any `pass_to_pass` test fails. Otherwise it is the share of `fail_to_pass` tests passing.
- Test results are read from JUnit XML. pytest, vitest and ctest can all produce it, so the same grader works for any of the three repos.
