#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${DOCMOLDER_VENV_DIR:-$(cd "${APP_DIR}/.." && pwd)/venv}"
ENV_FILE="${DOCMOLDER_ENV_FILE:-/etc/docmolder/docmolder.env}"
SERVICE_NAME="${DOCMOLDER_SERVICE_NAME:-docmolder}"
HEALTHCHECK_BIN="${DOCMOLDER_HEALTHCHECK_BIN:-${VENV_DIR}/bin/docmolder-healthcheck}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

cd "${APP_DIR}"
"${HEALTHCHECK_BIN}" \
  --check-service-active \
  --service-name "${SERVICE_NAME}"
