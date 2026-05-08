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

sudo apt update
sudo apt install -y python3 python3-venv python3-pip git ghostscript libreoffice-calc python3-uno

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  sudo useradd --system --create-home --home /var/lib/docmolder --shell /usr/sbin/nologin "${APP_USER}"
fi

sudo mkdir -p "${APP_ROOT}" "${ENV_DIR}" "${DATA_DIR}"
sudo chown -R "${APP_USER}:${APP_GROUP}" "${APP_ROOT}"

if [ ! -d "${APP_DIR}/.git" ]; then
  sudo -u "${APP_USER}" git clone https://github.com/max23468/DocMolder.git "${APP_DIR}"
else
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch origin
  sudo -u "${APP_USER}" git -C "${APP_DIR}" reset --hard origin/main
fi

sudo -u "${APP_USER}" git config --global --add safe.directory "${APP_DIR}" || true

if [ ! -d "${VENV_DIR}" ]; then
  sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
fi

sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -e "${APP_DIR}"

if [ ! -f "${ENV_DIR}/docmolder.env" ]; then
  sudo cp "${APP_DIR}/.env.example" "${ENV_DIR}/docmolder.env"
  sudo sed -i "s#^DOCMOLDER_RUNTIME_DIR=.*#DOCMOLDER_RUNTIME_DIR=${DATA_DIR}#" "${ENV_DIR}/docmolder.env"
  sudo sed -i "s#^DOCMOLDER_DATABASE_PATH=.*#DOCMOLDER_DATABASE_PATH=${DATA_DIR}/docmolder.db#" "${ENV_DIR}/docmolder.env"
  sudo sed -i "s#^DOCMOLDER_SQLITE_BACKUP_DIR=.*#DOCMOLDER_SQLITE_BACKUP_DIR=${BACKUP_DIR}#" "${ENV_DIR}/docmolder.env"
  sudo chown root:root "${ENV_DIR}/docmolder.env"
  sudo chmod 600 "${ENV_DIR}/docmolder.env"
  echo "Creato ${ENV_DIR}/docmolder.env. Modifica il file prima di avviare il servizio."
fi

sudo cp "${APP_DIR}/deploy/docmolder.service" /etc/systemd/system/docmolder.service
sudo cp "${APP_DIR}/deploy/docmolder-db-backup.service" /etc/systemd/system/docmolder-db-backup.service
sudo cp "${APP_DIR}/deploy/docmolder-db-backup.timer" /etc/systemd/system/docmolder-db-backup.timer
sudo cp "${APP_DIR}/deploy/docmolder-alertcheck.service" /etc/systemd/system/docmolder-alertcheck.service
sudo cp "${APP_DIR}/deploy/docmolder-alertcheck.timer" /etc/systemd/system/docmolder-alertcheck.timer
sudo cp "${APP_DIR}/deploy/docmolder-reconcile.service" /etc/systemd/system/docmolder-reconcile.service
sudo cp "${APP_DIR}/deploy/docmolder-reconcile.timer" /etc/systemd/system/docmolder-reconcile.timer
sudo install -D -m 755 "${APP_DIR}/deploy/install-github-webhook.sh" /opt/docmolder/bin/install-github-webhook.sh
sudo systemctl daemon-reload
sudo bash "${APP_DIR}/deploy/install-static-site.sh"
sudo bash "${APP_DIR}/deploy/install-github-webhook.sh"

echo "Installazione completata."
echo "Prossimi passi:"
echo "1. Modifica ${ENV_DIR}/docmolder.env"
echo "2. Esegui: sudo systemctl enable --now docmolder"
echo "3. Esegui: sudo systemctl enable --now docmolder-db-backup.timer"
echo "4. Esegui: sudo systemctl enable --now docmolder-alertcheck.timer"
echo "5. Esegui: sudo systemctl enable --now docmolder-reconcile.timer"
echo "6. Controlla: sudo systemctl status docmolder"
echo "7. Log: sudo journalctl -u docmolder -f"
echo "8. Per gli update futuri usa: sudo ${APP_DIR}/deploy/update-vps.sh"
