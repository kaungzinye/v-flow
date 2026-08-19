## Environment

- Run tests with `.venv/bin/pytest` — the project venv (uv-managed Python 3.13) with vflow installed editable. Recreate it with `uv venv .venv --python 3.13 && uv pip install -e . pytest --python .venv/bin/python`.
- The shell has `python3` only; there is no `python` executable. Homebrew's Python 3.14 cannot bootstrap pip (expat mismatch) — use the venv or uv.
- pytest resolves imports through `pythonpath = ["src"]` in pyproject.toml, so the suite runs against the local checkout in worktrees too.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

This repository uses a single-context domain layout. See `docs/agents/domain.md`.
