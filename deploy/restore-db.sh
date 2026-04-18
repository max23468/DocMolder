#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Uso: sudo /opt/docmolder/app/deploy/restore-db.sh /percorso/del/backup.db.backup" >&2
  exit 1
fi

APP_USER="docmolder"
SERVICE_NAME="docmolder"
VENV_PYTHON="/opt/docmolder/venv/bin/python"
ENV_FILE="/etc/docmolder/docmolder.env"
BACKUP_PATH="$1"

set -a
source "${ENV_FILE}"
set +a

DATABASE_PATH="${DOCMOLDER_DATABASE_PATH}"

echo "[stop]"
sudo systemctl stop "${SERVICE_NAME}"
trap 'sudo systemctl start "${SERVICE_NAME}" >/dev/null 2>&1 || true' EXIT

echo "[restore]"
sudo -u "${APP_USER}" "${VENV_PYTHON}" -m docmolder.sqlite_backup restore \
  --backup-path "${BACKUP_PATH}" \
  --db-path "${DATABASE_PATH}"

echo "[start]"
sudo systemctl start "${SERVICE_NAME}"
trap - EXIT

echo "[status]"
sudo systemctl is-active "${SERVICE_NAME}"
