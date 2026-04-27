#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="${ROOT_DIR}/githooks"

if [ ! -d "${HOOKS_DIR}" ]; then
  echo "Missing hooks directory: ${HOOKS_DIR}" >&2
  exit 1
fi

git config core.hooksPath githooks
chmod +x "${HOOKS_DIR}/pre-commit" "${HOOKS_DIR}/pre-push"

echo "Git hooks installed: ${HOOKS_DIR}"
