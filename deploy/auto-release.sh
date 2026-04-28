#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DOCMOLDER_VPS_APP_DIR:-/opt/docmolder/app}"
APP_USER="${DOCMOLDER_APP_USER:-docmolder}"
VENV_PYTHON="${DOCMOLDER_VENV_PYTHON:-/opt/docmolder/venv/bin/python}"
ENV_FILE="${DOCMOLDER_AUTO_RELEASE_ENV_FILE:-/etc/docmolder/release.env}"
SECRETS_ENV_FILE=""

cleanup() {
  if [ -n "${SECRETS_ENV_FILE}" ] && [ -f "${SECRETS_ENV_FILE}" ]; then
    rm -f "${SECRETS_ENV_FILE}"
  fi
}
trap cleanup EXIT

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
  custom_git_token_env="${DOCMOLDER_RELEASE_GIT_TOKEN_ENV:-}"
  if [ -n "${custom_git_token_env}" ] && [ "${custom_git_token_env}" != "DOCMOLDER_RELEASE_GIT_TOKEN" ]; then
    case "${custom_git_token_env}" in
      *[!A-Za-z0-9_]*)
        echo "Invalid DOCMOLDER_RELEASE_GIT_TOKEN_ENV: ${custom_git_token_env}" >&2
        exit 2
        ;;
    esac
  fi

  SECRETS_ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/docmolder-auto-release-env.XXXXXX")"
  chmod 600 "${SECRETS_ENV_FILE}"
  cp "${ENV_FILE}" "${SECRETS_ENV_FILE}"
  chown "${APP_USER}" "${SECRETS_ENV_FILE}"

  sudo -u "${APP_USER}" "${args[@]}" --secrets-env-file "${SECRETS_ENV_FILE}"
  exit $?
fi

exec "${args[@]}"
