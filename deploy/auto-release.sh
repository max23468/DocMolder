#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DOCMOLDER_VPS_APP_DIR:-/opt/docmolder/app}"
VENV_PYTHON="${DOCMOLDER_VENV_PYTHON:-/opt/docmolder/venv/bin/python}"
ENV_FILE="${DOCMOLDER_AUTO_RELEASE_ENV_FILE:-/etc/docmolder/release.env}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Auto release env missing: ${ENV_FILE}; skipping."
  exit 0
fi

set -a
source "${ENV_FILE}"
set +a

case "${DOCMOLDER_AUTO_RELEASE_ENABLED:-false}" in
  1|true|TRUE|yes|YES) ;;
  *)
    echo "Auto release disabled; skipping."
    exit 0
    ;;
esac

cd "${APP_DIR}"

exec "${VENV_PYTHON}" "${APP_DIR}/scripts/auto_release.py" \
  --repo-dir "${APP_DIR}" \
  --repository "${DOCMOLDER_RELEASE_REPOSITORY:-max23468/DocMolder}" \
  --branch "${DOCMOLDER_RELEASE_BRANCH:-main}" \
  --author-name "${DOCMOLDER_RELEASE_GIT_AUTHOR_NAME:-docmolder-release-bot}" \
  --author-email "${DOCMOLDER_RELEASE_GIT_AUTHOR_EMAIL:-docmolder-release-bot@users.noreply.github.com}"
