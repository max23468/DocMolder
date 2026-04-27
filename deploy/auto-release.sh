#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DOCMOLDER_VPS_APP_DIR:-/opt/docmolder/app}"
APP_USER="${DOCMOLDER_APP_USER:-docmolder}"
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

args=(
  "${VENV_PYTHON}" "${APP_DIR}/scripts/auto_release.py"
  --repo-dir "${APP_DIR}" \
  --repository "${DOCMOLDER_RELEASE_REPOSITORY:-max23468/DocMolder}" \
  --branch "${DOCMOLDER_RELEASE_BRANCH:-main}" \
  --git-token-env "${DOCMOLDER_RELEASE_GIT_TOKEN_ENV:-DOCMOLDER_RELEASE_GIT_TOKEN}" \
  --author-name "${DOCMOLDER_RELEASE_GIT_AUTHOR_NAME:-docmolder-release-bot}" \
  --author-email "${DOCMOLDER_RELEASE_GIT_AUTHOR_EMAIL:-docmolder-release-bot@users.noreply.github.com}"
)

if [ "$(id -u)" -eq 0 ] && id "${APP_USER}" >/dev/null 2>&1; then
  preserve_env="DOCMOLDER_RELEASE_GITHUB_TOKEN,DOCMOLDER_RELEASE_GIT_TOKEN,DOCMOLDER_RELEASE_GIT_TOKEN_ENV"
  custom_git_token_env="${DOCMOLDER_RELEASE_GIT_TOKEN_ENV:-}"
  if [ -n "${custom_git_token_env}" ] && [ "${custom_git_token_env}" != "DOCMOLDER_RELEASE_GIT_TOKEN" ]; then
    case "${custom_git_token_env}" in
      *[!A-Za-z0-9_]*)
        echo "Invalid DOCMOLDER_RELEASE_GIT_TOKEN_ENV: ${custom_git_token_env}" >&2
        exit 2
        ;;
      *)
        preserve_env="${preserve_env},${custom_git_token_env}"
        ;;
    esac
  fi
  exec sudo --preserve-env="${preserve_env}" -u "${APP_USER}" "${args[@]}"
fi

exec "${args[@]}"
