#!/usr/bin/env bash
set -euo pipefail

APP_USER="docmolder"
APP_DIR="/opt/docmolder/app"
VENV_DIR="/opt/docmolder/venv"
SERVICE_NAME="docmolder"
TARGET_REF="${1:-origin/main}"

ensure_excel_system_dependencies() {
  if command -v soffice >/dev/null 2>&1 && python3 -c "import uno" >/dev/null 2>&1; then
    return
  fi

  echo "[system deps]"
  if command -v apt >/dev/null 2>&1; then
    sudo apt update
    sudo apt install -y libreoffice-calc python3-uno
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y libreoffice-calc python3-uno || sudo dnf install -y libreoffice-calc libreoffice-pyuno
    return
  fi

  if command -v yum >/dev/null 2>&1; then
    sudo yum install -y libreoffice-calc python3-uno || sudo yum install -y libreoffice-calc libreoffice-pyuno
    return
  fi

  echo "LibreOffice dependencies missing and no supported package manager was found." >&2
  exit 1
}

sudo -u "${APP_USER}" git config --global --add safe.directory "${APP_DIR}" >/dev/null 2>&1 || true

cd "${APP_DIR}"

echo "[fetch]"
sudo -u "${APP_USER}" git fetch origin

echo "[reset]"
sudo -u "${APP_USER}" git reset --hard "${TARGET_REF}"

echo "[install]"
ensure_excel_system_dependencies
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -e "${APP_DIR}"

echo "[systemd]"
sudo cp "${APP_DIR}/deploy/docmolder.service" /etc/systemd/system/docmolder.service
sudo cp "${APP_DIR}/deploy/docmolder-db-backup.service" /etc/systemd/system/docmolder-db-backup.service
sudo cp "${APP_DIR}/deploy/docmolder-db-backup.timer" /etc/systemd/system/docmolder-db-backup.timer
sudo cp "${APP_DIR}/deploy/docmolder-alertcheck.service" /etc/systemd/system/docmolder-alertcheck.service
sudo cp "${APP_DIR}/deploy/docmolder-alertcheck.timer" /etc/systemd/system/docmolder-alertcheck.timer
sudo cp "${APP_DIR}/deploy/docmolder-reconcile.service" /etc/systemd/system/docmolder-reconcile.service
sudo cp "${APP_DIR}/deploy/docmolder-reconcile.timer" /etc/systemd/system/docmolder-reconcile.timer
sudo cp "${APP_DIR}/deploy/docmolder-duckdns.service" /etc/systemd/system/docmolder-duckdns.service
sudo cp "${APP_DIR}/deploy/docmolder-duckdns.timer" /etc/systemd/system/docmolder-duckdns.timer
sudo install -D -m 755 "${APP_DIR}/deploy/install-github-webhook.sh" /opt/docmolder/bin/install-github-webhook.sh
sudo install -D -m 755 "${APP_DIR}/deploy/update-duckdns.sh" /opt/docmolder/bin/update-duckdns.sh
sudo mkdir -p /etc/systemd/journald.conf.d
sudo cp "${APP_DIR}/deploy/docmolder-journald.conf" /etc/systemd/journald.conf.d/docmolder.conf
sudo bash "${APP_DIR}/deploy/install-static-site.sh"
sudo \
  DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER="${DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER:-}" \
  DOCMOLDER_GITHUB_WEBHOOK_RESTART_MARKER="${DOCMOLDER_GITHUB_WEBHOOK_RESTART_MARKER:-}" \
  bash "${APP_DIR}/deploy/install-github-webhook.sh"
sudo systemctl daemon-reload
sudo systemctl try-restart systemd-journald.service || true
sudo systemctl enable --now docmolder-db-backup.timer
sudo systemctl enable --now docmolder-alertcheck.timer
sudo systemctl enable --now docmolder-reconcile.timer
if [ -f /etc/docmolder/duckdns.env ]; then
  sudo systemctl enable --now docmolder-duckdns.timer
fi

echo "[restart]"
sudo systemctl restart "${SERVICE_NAME}"

echo "[status]"
sudo systemctl is-active "${SERVICE_NAME}"
sudo systemctl is-active docmolder-alertcheck.timer
sudo systemctl is-active docmolder-reconcile.timer
sudo systemctl is-active docmolder-duckdns.timer || true

echo "[revision]"
sudo -u "${APP_USER}" git rev-parse --short HEAD
