#!/usr/bin/env bash
set -euo pipefail

COVERAGE_MODE="${1:---coverage}"
PYTHON_BIN="python3"
COVERAGE_BIN="coverage"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi
if [ -x ".venv/bin/coverage" ]; then
  COVERAGE_BIN=".venv/bin/coverage"
fi

case "${COVERAGE_MODE}" in
  --coverage)
    if command -v "${COVERAGE_BIN}" >/dev/null 2>&1; then
      "${COVERAGE_BIN}" erase
      "${COVERAGE_BIN}" run -m unittest discover -s tests
      "${COVERAGE_BIN}" report
      rm -f .coverage
    else
      echo "coverage non disponibile: eseguo unittest senza coverage." >&2
      "${PYTHON_BIN}" -m unittest discover -s tests
    fi
    ;;
  --no-coverage)
    "${PYTHON_BIN}" -m unittest discover -s tests
    ;;
  *)
    echo "Uso: scripts/ci_test.sh [--coverage|--no-coverage]" >&2
    exit 2
    ;;
esac
