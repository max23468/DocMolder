#!/usr/bin/env bash
set -euo pipefail

APP_USER="docmolder"
APP_DIR="/opt/docmolder/app"
VENV_DIR="/opt/docmolder/venv"
SERVICE_NAME="docmolder"
TARGET_REF="${1:-origin/main}"
PYTHON_BIN="${DOCMOLDER_PYTHON_BIN:-}"

# Serializza ogni deploy (webhook GitHub, timer di auto-deploy, manuale) sullo
# stesso lock: evita due `git reset --hard` + pip install + restart concorrenti.
# Attesa fino a 30 min, poi esce senza deployare (il chiamante ritentera').
DEPLOY_LOCK="${DOCMOLDER_DEPLOY_LOCK:-/run/docmolder-update-vps.lock}"
exec 9>"${DEPLOY_LOCK}"
if ! flock -w 1800 9; then
  echo "[update-vps] un altro deploy e' in corso da oltre 30 min; esco." >&2
  exit 1
fi

choose_python() {
  if [ -n "${PYTHON_BIN}" ]; then
    if [ ! -x "${PYTHON_BIN}" ]; then
      echo "Configured DOCMOLDER_PYTHON_BIN is not executable: ${PYTHON_BIN}" >&2
      exit 1
    fi
  else
    for candidate in python3.13 python3.12 python3.11 python3; do
      if command -v "${candidate}" >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v "${candidate}")"
        break
      fi
    done
  fi

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
      echo "Unsupported Python version ${version}; DocMolder requires Python 3.11, 3.12, or 3.13." >&2
      exit 1
      ;;
  esac
}

venv_matches_selected_python() {
  if [ ! -x "${VENV_DIR}/bin/python" ]; then
    return 1
  fi

  local selected_version version
  selected_version="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  version="$("${VENV_DIR}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  [ "${version}" = "${selected_version}" ]
}

ensure_venv() {
  if venv_matches_selected_python; then
    return
  fi

  echo "[venv] recreating with ${PYTHON_BIN}"
  sudo systemctl stop "${SERVICE_NAME}" || true
  sudo rm -rf "${VENV_DIR}"
  sudo -u "${APP_USER}" "${PYTHON_BIN}" -m venv "${VENV_DIR}"
}

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
choose_python
ensure_venv
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --require-hashes -r "${APP_DIR}/requirements.lock"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -e "${APP_DIR}" --no-deps

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
sudo cp "${APP_DIR}/deploy/docmolder-autodeploy.service" /etc/systemd/system/docmolder-autodeploy.service
sudo cp "${APP_DIR}/deploy/docmolder-autodeploy.timer" /etc/systemd/system/docmolder-autodeploy.timer
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
sudo systemctl enable --now docmolder-autodeploy.timer
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
