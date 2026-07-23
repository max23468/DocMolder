#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

if command -v uv >/dev/null 2>&1; then
  if ! uv pip compile pyproject.toml --universal --generate-hashes --no-header -o - 2>/dev/null \
    | diff -u requirements.lock - >/dev/null; then
    echo "requirements.lock non e' allineato a pyproject.toml: esegui 'make lock' e ricommitta." >&2
    exit 1
  fi
else
  echo "uv non disponibile: salto il check di sincronia di requirements.lock." >&2
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
