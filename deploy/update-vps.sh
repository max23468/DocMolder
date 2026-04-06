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

echo "[restart]"
sudo systemctl restart "${SERVICE_NAME}"

echo "[status]"
sudo systemctl is-active "${SERVICE_NAME}"

echo "[revision]"
sudo -u "${APP_USER}" git rev-parse --short HEAD
