#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${DOCMOLDER_ENV_FILE:-/etc/docmolder/docmolder.env}"
DATABASE_PATH="${DOCMOLDER_DATABASE_PATH:-/opt/docmolder/data/runtime/docmolder.db}"
RUNTIME_DIR="${DOCMOLDER_RUNTIME_DIR:-/opt/docmolder/data/runtime}"
BACKUP_DIR="${DOCMOLDER_SQLITE_BACKUP_DIR:-/opt/docmolder/data/runtime/backups}"

check_file_mode() {
  local path="$1"
  local expected="$2"

  if [ ! -e "${path}" ]; then
    echo "MISSING ${path}"
    return 1
  fi

  local actual
  actual="$(stat -c '%a' "${path}")"
  if [ "${actual}" != "${expected}" ]; then
    echo "BADMODE ${path} expected=${expected} actual=${actual}"
    return 1
  fi

  echo "OK ${path} mode=${actual}"
}

check_dir_exists() {
  local path="$1"
  if [ ! -d "${path}" ]; then
    echo "MISSING_DIR ${path}"
    return 1
  fi
  echo "OK ${path}"
}

status=0
check_file_mode "${ENV_FILE}" "600" || status=1
check_dir_exists "${RUNTIME_DIR}" || status=1
check_dir_exists "${BACKUP_DIR}" || status=1

if [ -e "${DATABASE_PATH}" ]; then
  db_mode="$(stat -c '%a' "${DATABASE_PATH}")"
  case "${db_mode}" in
    600|660|640)
      echo "OK ${DATABASE_PATH} mode=${db_mode}"
      ;;
    *)
      echo "BADMODE ${DATABASE_PATH} expected=600_or_640_or_660 actual=${db_mode}"
      status=1
      ;;
  esac
else
  echo "SKIP ${DATABASE_PATH} missing"
fi

exit "${status}"
