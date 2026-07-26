#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"
constraints="$(mktemp)"
trap 'rm -f "${constraints}"' EXIT

sed -nE '/^[[:alnum:]_.-]+==/ { s/[[:space:]]*\\$//; p; }' requirements.lock >"${constraints}"
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install --require-hashes -r requirements.lock
"${PYTHON_BIN}" -m pip install -e ".[dev]" --constraint "${constraints}"
