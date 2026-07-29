#!/usr/bin/env bash
set -euo pipefail

VENV_PYTHON="/opt/docmolder/venv/bin/python"
ENV_FILE="/etc/docmolder/docmolder.env"

if [ -r "${ENV_FILE}" ]; then
  set -a
  source "${ENV_FILE}"
  set +a
fi

DATABASE_PATH="${DOCMOLDER_DATABASE_PATH}"
BACKUP_DIR="${DOCMOLDER_SQLITE_BACKUP_DIR:-${DOCMOLDER_RUNTIME_DIR%/}/backups}"
RETENTION_DAYS="${DOCMOLDER_SQLITE_BACKUP_RETENTION_DAYS:-7}"

"${VENV_PYTHON}" -m docmolder.sqlite_backup backup \
  --db-path "${DATABASE_PATH}" \
  --backup-dir "${BACKUP_DIR}" \
  --retention-days "${RETENTION_DAYS}"
