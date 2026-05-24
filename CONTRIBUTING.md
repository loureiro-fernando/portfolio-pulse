# Contributing to Portfolio-Pulse

This is a portfolio project, not a community-driven OSS library. That said, it is built like one and PRs that fix bugs or improve clarity are welcome.

## Setup

See `RUNBOOK.md` "Cold start" - 8 commands and you have a running stack.

## Workflow

1. Branch from `main`: `git checkout -b fix/short-description`
2. Make changes
3. Run locally: `make lint && make test` - both must pass before commit
4. Commit: granular messages, conventional prefix (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`)
5. Push and open PR

## Pre-commit hooks

Installed via `pre-commit install`. On every `git commit` they run:

- `gitleaks` (blocks anything that looks like a secret)
- `ruff check --fix` (lint with autofix)
- `ruff format` (Black-equivalent formatting)
- trailing whitespace, end-of-file newline, large file check

If a hook fails, fix the issue and re-stage. Do not bypass with `--no-verify` - if a secret slipped, rotate the secret before recommitting.

## Tests

```bash
pytest -q                                  # unit tests in tests/ (no I/O)
pytest skills/portco-anomaly-monitor/evals # eval suite for the Skill
pytest skills/lp-update-drafter/evals      # eval suite for the LP drafter Skill
```

CI runs only `pytest -q`. The skill evals are run on-demand because they mock the Anthropic client (no real cost) but live in `skills/` which `pyproject.toml` excludes from default test collection.

## Code style

- Python 3.12+ idioms: `dict[K, V]`, `list[T]`, `T | None`, `str | None`. No `from __future__ import annotations`.
- 100 char line limit (`tool.ruff line-length`).
- Type hints everywhere. `mypy app/` is part of the lint check; treat new errors as a regression.
- Async by default in `app/`. The DB engine, the Anthropic client, Slack client are all async.
- No emojis in code or commits. The project uses plain ASCII; emojis are reserved for Slack messages (severity icons) where users expect them.

## Architectural changes

If you are about to add a new agent, a new tool, or a new model, **read `ARCHITECTURE.md` first**. The ADR-light sections (ADR-001..009) document the constraints behind the current shape. If your change contradicts one, update or supersede the ADR in the same PR.

## Bumping dependencies

`pyproject.toml` pins minimum versions, not exact. To bump:

```bash
source .venv/bin/activate
pip install -U --upgrade-strategy eager -e ".[dev]"
make test                                  # all 60+ tests should still pass
pre-commit autoupdate                      # bump pre-commit hook versions
```

If something breaks, file an issue with the dep + traceback before downgrading.

## Releasing

```bash
git tag -a v0.X.Y -m "release notes"
git push origin v0.X.Y
```

Tag from `main`, signed if you have GPG configured. Each tag triggers a fresh CI run.

## What is out of scope

- Production hardening (RLS, real auth, queue, observability backend that is not Jaeger)
- Real PitchBook / Egnyte integrations (they are mocks by design)
- Mobile / React Native client
- Multiple LLM providers (the project demonstrates Anthropic native; abstracting would defeat the purpose)
