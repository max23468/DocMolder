#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

"${PYTHON_BIN}" -m pip install --require-hashes -r requirements-build.lock
"${PYTHON_BIN}" -m pip install --require-hashes -r requirements-dev.lock
"${PYTHON_BIN}" -m pip install -e . --no-deps --no-build-isolation
