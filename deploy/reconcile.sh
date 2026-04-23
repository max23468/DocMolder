#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${DOCMOLDER_VENV_DIR:-$(cd "${APP_DIR}/.." && pwd)/venv}"
ENV_FILE="${DOCMOLDER_ENV_FILE:-/etc/docmolder/docmolder.env}"
RECONCILE_BIN="${DOCMOLDER_RECONCILE_BIN:-${VENV_DIR}/bin/docmolder-reconcile}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

cd "${APP_DIR}"
exec "${RECONCILE_BIN}"
