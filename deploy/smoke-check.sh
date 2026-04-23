#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${DOCMOLDER_VENV_DIR:-$(cd "${APP_DIR}/.." && pwd)/venv}"
ENV_FILE="${DOCMOLDER_ENV_FILE:-/etc/docmolder/docmolder.env}"
SERVICE_NAME="${DOCMOLDER_SERVICE_NAME:-docmolder}"
HEALTHCHECK_BIN="${DOCMOLDER_HEALTHCHECK_BIN:-${VENV_DIR}/bin/docmolder-healthcheck}"
ATTEMPTS="${DOCMOLDER_SMOKE_CHECK_ATTEMPTS:-12}"
SLEEP_SECONDS="${DOCMOLDER_SMOKE_CHECK_SLEEP_SECONDS:-5}"

if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

cd "${APP_DIR}"
for attempt in $(seq 1 "${ATTEMPTS}"); do
  if "${HEALTHCHECK_BIN}" --check-service-active --service-name "${SERVICE_NAME}"; then
    echo "DocMolder smoke check OK."
    exit 0
  fi
  if [ "${attempt}" -eq "${ATTEMPTS}" ]; then
    echo "DocMolder smoke check non stabile dopo ${ATTEMPTS} tentativi." >&2
    exit 1
  fi
  echo "Healthcheck non ancora stabile (${attempt}/${ATTEMPTS}), nuovo tentativo tra ${SLEEP_SECONDS}s..."
  sleep "${SLEEP_SECONDS}"
done
