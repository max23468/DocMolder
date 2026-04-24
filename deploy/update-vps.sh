#!/usr/bin/env bash
set -euo pipefail

APP_USER="docmolder"
APP_DIR="/opt/docmolder/app"
VENV_DIR="/opt/docmolder/venv"
SERVICE_NAME="docmolder"
TARGET_REF="${1:-origin/main}"

sudo -u "${APP_USER}" git config --global --add safe.directory "${APP_DIR}" >/dev/null 2>&1 || true

cd "${APP_DIR}"

echo "[fetch]"
sudo -u "${APP_USER}" git fetch origin

echo "[reset]"
sudo -u "${APP_USER}" git reset --hard "${TARGET_REF}"

echo "[install]"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -e "${APP_DIR}"

echo "[systemd]"
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

echo "[restart]"
sudo systemctl restart "${SERVICE_NAME}"

echo "[status]"
sudo systemctl is-active "${SERVICE_NAME}"
sudo systemctl is-active docmolder-alertcheck.timer
sudo systemctl is-active docmolder-reconcile.timer

echo "[revision]"
sudo -u "${APP_USER}" git rev-parse --short HEAD
