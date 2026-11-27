# Task Factory: Innodata AI Hackathon, Track 1

Turns a repository into validated Harbor 0.25 feature-development task packages.

## Results (27 Nov 2026)
| Task | fail_to_pass | pass_to_pass | nop | oracle | mutants killed | made by |
|---|---|---|---|---|---|---|
| duration-param-type | 26 | 2,434 | 0.0 | 1.0 | 25/25 | hand-written seed spec |
| byte-size | 29 | 2,434 | 0.0 | 1.0 | 36/37 | qwen2.5-coder:7b + test fix after mutation testing |
| kebab-case | 14 | 2,434 | 0.0 | 1.0 | 11/12 | qwen2.5-coder:7b |
| key-value-pairs | 15 | 2,434 | 0.0 | 1.0 | 5/6 | qwen2.5-coder:7b, instruction reviewed |
| semver | 14 | 2,434 | 0.0 | 1.0 | 36/40 | qwen2.5-coder:7b, instruction reviewed |

nop and oracle are from real `harbor run` jobs. Each manual change is listed in `specs/click/<slug>/REVIEW.md`. Rejected drafts are in `specs_rejected/`. For example, `ip-address` imported `ipaddress` at module load and broke click's `test_light_imports`, so the regression guardrail rejected it. Before recorded test values (runs 1 to 13), 1 draft in about 12 passed. With them, run 14 validated 3 of 4 drafts on the first attempt.

## Layout
```
repos/<name>.toml          everything repo-specific (url, base_commit, test_cmd, Dockerfile)
specs/<repo>/<slug>/       one task spec: instruction.md, solution.patch, feature/ tests, meta.toml
factory/build.py           spec -> Harbor package, validated in the task's own Docker image
factory/grade.py           grader shipped inside every task (stdlib only)
factory/mutate.py          mutation testing of a spec's feature tests
tasks/                     generated Harbor task packages
evidence/                  per-task logs, JUnit XML, validation reports
work/                      repo clones (not committed)
```

## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install "harbor==0.25.*" pytest pyflakes
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
The default backend is free and local: Ollama with `qwen2.5-coder:7b` (`TF_OLLAMA_MODEL`). A 7B model can't edit existing code reliably, so `factory/local_llm.py` drives it in small steps: (1) one new module, which the factory exports; (2) tests: the model only picks test inputs (Python expressions) and the factory runs them against the implementation to record the expected values, because a 7B model can't predict outputs reliably; (3) the requirement document, written from the code and tests. With `TF_BACKEND=claude`, headless Claude Code (`claude -p`, model `TF_MODEL`, default `opus`) instead proposes features, then implements each one in a throwaway git worktree: the source change, a new test file and `TASK_INSTRUCTION.md`. Each draft has to pass these guardrails before it becomes a task:

| Stage | Guardrail |
|---|---|
| Proposal | its (area, change_kind) differs from every existing task; any new public names must not already exist upstream (`origin/main`) |
| Extraction | tests must be new files (no edits to existing tests); the patch may only touch `source_paths`; the instruction must not leak code or test file names |
| Validation | `factory.build` in Docker: nop 0.0, oracle 1.0, no regressions. On failure the agent gets the problems back, for up to `--repairs` rounds |

Every decision is logged to `evidence/generation_log.jsonl`. Failed drafts are moved to `specs_rejected/`.
Self-check for the non-AI path: `.venv/bin/python -m pytest -q -p no:anyio factory/test_generate.py`.

## Mutation testing
```bash
.venv/bin/python -m factory.mutate repos/click.toml specs/click/byte-size
```
Applies the reference patch, then mutates only the lines it added (flipped comparisons, swapped operators, off-by-one constants, `and`/`or`, dropped `not`, `return None`). Each mutant must make the feature tests fail. Results go to `evidence/<repo>-<slug>/mutation.json`. The generator runs this on every valid Python task. Survivors are reviewed by a person; fixes are written down in `specs/<repo>/<slug>/REVIEW.md`.

## Harbor validation
```bash
harbor run -p tasks/click-duration-param-type -a nop    -k 1 -o jobs/nop    --no-delete -y   # expect 0.0
harbor run -p tasks/click-duration-param-type -a oracle -k 1 -o jobs/oracle --no-delete -y   # expect 1.0
```

## Grading
- The verifier runs in a **separate** container. The agent's work is passed across only as `git diff`, which `[[verifier.collect]]` saves to `/logs/artifacts/agent.patch`.
- Reward is 0.0 if any `pass_to_pass` test fails. Otherwise it is the share of `fail_to_pass` tests passing.
- Test results are read from JUnit XML. pytest, vitest and ctest can all produce it, so the same grader works for any of the three repos.
