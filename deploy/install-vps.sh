#!/usr/bin/env bash
set -euo pipefail

APP_USER="docmolder"
APP_GROUP="docmolder"
APP_ROOT="/opt/docmolder"
APP_DIR="${APP_ROOT}/app"
VENV_DIR="${APP_ROOT}/venv"
DATA_DIR="${APP_ROOT}/data/runtime"
BACKUP_DIR="${DATA_DIR}/backups"
ENV_DIR="/etc/docmolder"
ENV_FILE="${ENV_DIR}/docmolder.env"
PYTHON_BIN=""

install_packages() {
  if command -v apt >/dev/null 2>&1; then
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv python3-pip git ghostscript || sudo apt install -y python3 python3-venv python3-pip git ghostscript
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3.11 python3.11-pip git ghostscript || sudo dnf install -y python3 python3-pip git ghostscript
    return
  fi

  if command -v yum >/dev/null 2>&1; then
    sudo yum install -y python3.11 python3.11-pip git ghostscript || sudo yum install -y python3 python3-pip git ghostscript
    return
  fi

  echo "Unsupported package manager: expected apt, dnf, or yum." >&2
  exit 1
}

choose_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "${candidate}")"
      break
    fi
  done

  if [ -z "${PYTHON_BIN}" ]; then
    echo "No supported Python interpreter found." >&2
    exit 1
  fi

  local version
  version="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  case "${version}" in
    3.11|3.12|3.13)
      ;;
    *)
      echo "Unsupported Python version ${version}; DocMolder requires >=3.11." >&2
      exit 1
      ;;
  esac
}

venv_python_supported() {
  if [ ! -x "${VENV_DIR}/bin/python" ]; then
    return 1
  fi

  local version
  version="$("${VENV_DIR}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  case "${version}" in
    3.11|3.12|3.13)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

install_packages
choose_python

if ! getent group "${APP_GROUP}" >/dev/null 2>&1; then
  sudo groupadd --system "${APP_GROUP}"
fi

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  sudo useradd --system --create-home --home /var/lib/docmolder --shell /usr/sbin/nologin --gid "${APP_GROUP}" "${APP_USER}"
fi

sudo mkdir -p "${APP_ROOT}" "${ENV_DIR}" "${DATA_DIR}" "${BACKUP_DIR}"
sudo chown -R "${APP_USER}:${APP_GROUP}" "${APP_ROOT}"

if [ -d "${VENV_DIR}" ] && ! venv_python_supported; then
  sudo rm -rf "${VENV_DIR}"
fi

if [ ! -d "${VENV_DIR}" ]; then
  sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -e "${APP_DIR}"

if [ ! -f "${ENV_FILE}" ]; then
  sudo cp "${APP_DIR}/.env.example" "${ENV_FILE}"
fi

sudo sed -i "s#^DOCMOLDER_RUNTIME_DIR=.*#DOCMOLDER_RUNTIME_DIR=${DATA_DIR}#" "${ENV_FILE}"
sudo sed -i "s#^DOCMOLDER_DATABASE_PATH=.*#DOCMOLDER_DATABASE_PATH=${DATA_DIR}/docmolder.db#" "${ENV_FILE}"
sudo sed -i "s#^DOCMOLDER_SQLITE_BACKUP_DIR=.*#DOCMOLDER_SQLITE_BACKUP_DIR=${BACKUP_DIR}#" "${ENV_FILE}"
sudo chown root:root "${ENV_FILE}"
sudo chmod 600 "${ENV_FILE}"

sudo cp "${APP_DIR}/deploy/docmolder.service" /etc/systemd/system/docmolder.service
sudo cp "${APP_DIR}/deploy/docmolder-db-backup.service" /etc/systemd/system/docmolder-db-backup.service
sudo cp "${APP_DIR}/deploy/docmolder-db-backup.timer" /etc/systemd/system/docmolder-db-backup.timer
sudo cp "${APP_DIR}/deploy/docmolder-alertcheck.service" /etc/systemd/system/docmolder-alertcheck.service
sudo cp "${APP_DIR}/deploy/docmolder-alertcheck.timer" /etc/systemd/system/docmolder-alertcheck.timer
sudo cp "${APP_DIR}/deploy/docmolder-reconcile.service" /etc/systemd/system/docmolder-reconcile.service
sudo cp "${APP_DIR}/deploy/docmolder-reconcile.timer" /etc/systemd/system/docmolder-reconcile.timer
sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp "${APP_DIR}/deploy/docmolder-journald.conf" /etc/systemd/journald.conf.d/docmolder.conf
sudo systemctl daemon-reload
sudo systemctl try-restart systemd-journald.service || true
sudo systemctl enable --now docmolder-db-backup.timer
sudo systemctl enable --now docmolder-alertcheck.timer
sudo systemctl enable --now docmolder-reconcile.timer

if sudo grep -q '^DOCMOLDER_TELEGRAM_TOKEN=changeme$' "${ENV_FILE}" || sudo grep -q '^DOCMOLDER_TELEGRAM_TOKEN=$' "${ENV_FILE}"; then
  echo "Environment file created at ${ENV_FILE}. Set DOCMOLDER_TELEGRAM_TOKEN before starting docmolder."
  exit 0
fi

sudo systemctl enable --now docmolder
sudo systemctl restart docmolder

echo "[status]"
sudo systemctl is-active docmolder
sudo systemctl is-active docmolder-db-backup.timer
sudo systemctl is-active docmolder-alertcheck.timer
sudo systemctl is-active docmolder-reconcile.timer
