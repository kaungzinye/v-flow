#!/usr/bin/env bash
set -euo pipefail

echo "v-flow installer"
echo "----------------"

# Determine where to load skills from.
# If the script is on disk (run from a checkout), use that directory.
# If it's being piped via curl, download the repo archive to a temp directory.
if [ -n "${BASH_SOURCE-}" ] && [ -n "${BASH_SOURCE[0]-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  REPO_ROOT="${SCRIPT_DIR}"
else
  echo "No local script path detected, downloading v-flow skills from GitHub..."
  TMP_DIR="$(mktemp -d)"
  curl -fsSL https://github.com/kaungzinye/v-flow/archive/refs/heads/main.tar.gz \
    | tar -xz -C "${TMP_DIR}"
  REPO_ROOT="${TMP_DIR}/v-flow-main"
fi

SKILLS_SRC="${REPO_ROOT}/skills"

if [ ! -d "${SKILLS_SRC}" ]; then
  echo "Error: skills directory not found at ${SKILLS_SRC}."
  echo "Make sure the v-flow repo is available, or re-run this installer from the published URL."
  exit 1
fi

# Choose a Python interpreter
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Error: python3 (or python) is required to install v-flow."
    exit 1
  fi
fi

echo
echo "1) Installing or upgrading vflow-cli via pip (provides the v-flow command)..."
"${PYTHON_BIN}" -m pip install --upgrade vflow-cli

echo
echo "2) Installing v-flow skills for Claude Code and Cursor (if present)..."

TARGETS=()

# Claude Code personal skills directory
TARGETS+=("$HOME/.claude/skills")

# Cursor global skills directory
TARGETS+=("$HOME/.cursor/skills")

for TARGET in "${TARGETS[@]}"; do
  echo
  echo "-> Installing skills into: ${TARGET}"
  mkdir -p "${TARGET}"

  for SKILL_DIR in "${SKILLS_SRC}"/*; do
    [ -d "${SKILL_DIR}" ] || continue
    NAME="$(basename "${SKILL_DIR}")"
    DEST="${TARGET}/${NAME}"

    rm -rf "${DEST}"
    cp -R "${SKILL_DIR}" "${DEST}"
    echo "   - Installed skill: ${NAME}"
  done
done

cat <<'EOF'

Done.

Next steps:
- Open Claude Code or Cursor.
- Start a new chat in a project where these skills should be available.
- Try natural prompts like:
  - "Ingest my card and set up a project on my SSD."
  - "Back up my ingest folder and free up space."
  - "Show me duplicate clips from the last day."

The v-flow skills will orchestrate the local `v-flow` CLI using your ~/.vflow_config.yml.
EOF

