#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

bash scripts/ci_static_verify.sh
bash scripts/ci_quality.sh
bash scripts/ci_test.sh --coverage

if "${PYTHON_BIN}" -m build --version >/dev/null 2>&1; then
  build_dir="$(mktemp -d)"
  trap 'rm -rf "${build_dir}"' EXIT
  "${PYTHON_BIN}" -m build --outdir "${build_dir}"
else
  echo "build non disponibile: salto package build locale." >&2
fi
