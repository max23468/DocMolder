#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python3"
RUFF_BIN="ruff"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [ -x ".venv/bin/ruff" ]; then
  RUFF_BIN=".venv/bin/ruff"
fi

"${PYTHON_BIN}" -m compileall src tests

if command -v "${RUFF_BIN}" >/dev/null 2>&1; then
  "${RUFF_BIN}" check src tests
else
  echo "ruff non disponibile: salto lint." >&2
fi
