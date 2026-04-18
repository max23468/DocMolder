#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST="${DOCMOLDER_VPS_HOST:-}"
USER_NAME="${DOCMOLDER_VPS_USER:-opc}"
PORT="${DOCMOLDER_VPS_PORT:-22}"
APP_DIR="${DOCMOLDER_VPS_APP_DIR:-/opt/docmolder/app}"
DEPLOY_CMD="${DOCMOLDER_VPS_DEPLOY_CMD:-sudo /opt/docmolder/app/deploy/update-vps.sh}"
TARGET_REF="${1:-origin/main}"

if [[ -z "${HOST}" ]]; then
  echo "Missing DOCMOLDER_VPS_HOST" >&2
  exit 1
fi

"${ROOT_DIR}/scripts/setup_codex_ssh.sh" >/dev/null

SSH_KEY_PATH="${HOME}/.ssh/docmolder_codex_vps"
SSH_OPTIONS=(
  -i "${SSH_KEY_PATH}"
  -p "${PORT}"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
)

if [[ -n "${DOCMOLDER_VPS_SSH_KNOWN_HOSTS:-}" ]]; then
  SSH_OPTIONS+=(
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile="${HOME}/.ssh/known_hosts"
  )
else
  SSH_OPTIONS+=(-o StrictHostKeyChecking=accept-new)
fi

REMOTE_SCRIPT=$(cat <<EOF
set -euo pipefail
${DEPLOY_CMD@Q} ${TARGET_REF@Q}
sudo systemctl is-active docmolder
sudo systemctl status docmolder --no-pager
sudo systemctl status docmolder-db-backup.timer --no-pager
sudo -u docmolder git -C ${APP_DIR@Q} rev-parse HEAD
EOF
)

ssh "${SSH_OPTIONS[@]}" "${USER_NAME}@${HOST}" "${REMOTE_SCRIPT}"
