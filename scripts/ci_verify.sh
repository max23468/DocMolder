#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python3"
RUFF_BIN="ruff"
COVERAGE_BIN="coverage"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [ -x ".venv/bin/ruff" ]; then
  RUFF_BIN=".venv/bin/ruff"
fi
if [ -x ".venv/bin/coverage" ]; then
  COVERAGE_BIN=".venv/bin/coverage"
fi

"${PYTHON_BIN}" -m compileall src tests

if command -v "${RUFF_BIN}" >/dev/null 2>&1; then
  "${RUFF_BIN}" check src tests
else
  echo "ruff non disponibile: salto lint." >&2
fi

if command -v "${COVERAGE_BIN}" >/dev/null 2>&1; then
  "${COVERAGE_BIN}" erase
  "${COVERAGE_BIN}" run -m unittest discover -s tests
  "${COVERAGE_BIN}" report
  rm -f .coverage
else
  "${PYTHON_BIN}" -m unittest discover -s tests
fi

if "${PYTHON_BIN}" -m build --version >/dev/null 2>&1; then
  build_dir="$(mktemp -d)"
  trap 'rm -rf "${build_dir}"' EXIT
  "${PYTHON_BIN}" -m build --outdir "${build_dir}"
else
  echo "build non disponibile: salto package build locale." >&2
fi
