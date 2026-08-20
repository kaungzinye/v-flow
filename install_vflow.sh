#!/usr/bin/env bash
set -euo pipefail

echo "v-flow installer"
echo "----------------"

SKILLS_ONLY=false
case "${1-}" in
  "") ;;
  --skills-only) SKILLS_ONLY=true ;;
  --help)
    echo "Usage: ./install_vflow.sh [--skills-only]"
    echo "  --skills-only  Refresh copied skills from this checkout without installing the CLI."
    exit 0
    ;;
  *)
    echo "Error: unknown option: $1"
    echo "Usage: ./install_vflow.sh [--skills-only]"
    exit 1
    ;;
esac

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

if [ "${SKILLS_ONLY}" = false ]; then
  echo
  echo "1) Installing or upgrading vflow-cli via pip (provides the v-flow command)..."
  "${PYTHON_BIN}" -m pip install --upgrade vflow-cli
else
  echo
  echo "1) Keeping the existing vflow-cli installation (--skills-only)."
fi

echo
echo "2) Refreshing v-flow skills for Codex, Claude Code, and Cursor..."

TARGETS=()

# Codex personal skills directory
TARGETS+=("${CODEX_HOME:-$HOME/.codex}/skills")

# Claude Code personal skills directory
TARGETS+=("$HOME/.claude/skills")

# Cursor global skills directory
TARGETS+=("$HOME/.cursor/skills")

RETIRED_SKILLS=(
  vflow
  vflow-backup-cleanup-assistant
  vflow-delivery-tagging-assistant
  vflow-ingest-project-assistant
  vflow-maintenance-assistant
  vflow-setup-assistant
)

for TARGET in "${TARGETS[@]}"; do
  echo
  echo "-> Refreshing skills in: ${TARGET}"
  mkdir -p "${TARGET}"

  for RETIRED_SKILL in "${RETIRED_SKILLS[@]}"; do
    RETIRED_DEST="${TARGET}/${RETIRED_SKILL}"
    if [ -d "${RETIRED_DEST}" ]; then
      rm -R -- "${RETIRED_DEST}"
      echo "   - Removed retired skill: ${RETIRED_SKILL}"
    fi
  done

  for SKILL_DIR in "${SKILLS_SRC}"/*; do
    [ -f "${SKILL_DIR}/SKILL.md" ] || continue
    NAME="$(basename "${SKILL_DIR}")"
    DEST="${TARGET}/${NAME}"

    if [ -d "${DEST}" ]; then
      rm -R -- "${DEST}"
    fi
    cp -R "${SKILL_DIR}" "${DEST}"
    echo "   - Installed skill: ${NAME}"
  done
done

cat <<'EOF'

Done.

Next steps:
- Open Codex, Claude Code, or Cursor.
- Start a new task and say: "Set up v-flow and explain each storage location as we go."
- Once configured, try prompts like:
  - "Copy this camera card somewhere safe, then put the footage on my SSD for editing."
  - "Save this finished video to my long-term storage and keep the local export."
  - "Remove the temporary editing footage after checking that the safe copy is complete."

The v-flow skills will orchestrate the local `v-flow` CLI using your ~/.vflow_config.yml.
EOF
