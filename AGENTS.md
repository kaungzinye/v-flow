## Environment

- Run tests with `.venv/bin/pytest`. Create the venv with `python3 -m venv .venv && .venv/bin/pip install -e . pytest` (or the `uv` equivalent).
- pytest resolves imports through `pythonpath = ["src"]` in pyproject.toml, so the suite runs against the local checkout even without an editable install.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

This repository uses a single-context domain layout. See `docs/agents/domain.md`.
