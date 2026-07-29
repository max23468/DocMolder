#!/usr/bin/env bash
set -euo pipefail

readonly APP_USER="docmolder"
readonly APP_GROUP="docmolder"
readonly APP_DIR="/opt/docmolder/app"
readonly VENV_DIR="/opt/docmolder/venv"
readonly ENV_FILE="/etc/docmolder/docmolder.env"
readonly SERVICE_NAME="docmolder"
readonly WEBHOOK_SERVICE="docmolder-github-webhook.service"
readonly WEBHOOK_ENV_FILE="/etc/docmolder/github-webhook.env"
readonly DEPLOY_LOCK="/run/docmolder-update-vps.lock"
readonly MODE="${1:-deploy}"
readonly TARGET_REF="${2:-origin/main}"

exec 9>"${DEPLOY_LOCK}"
if ! flock -w 1800 9; then
  echo "[update-vps] un altro deploy e' in corso da oltre 30 min; esco." >&2
  exit 1
fi

if [ "${MODE}" != "deploy" ] && [ "${MODE}" != "rollback" ]; then
  echo "[update-vps] modalita' non consentita: usa deploy o rollback." >&2
  exit 1
fi
if [ "${TARGET_REF}" != "origin/main" ] && [[ ! "${TARGET_REF}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "[update-vps] target non consentito: usa origin/main o uno SHA completo." >&2
  exit 1
fi

cd "${APP_DIR}"
chown root:"${APP_GROUP}" "${ENV_FILE}"
chmod 640 "${ENV_FILE}"
previous_sha="$(sudo -u "${APP_USER}" git rev-parse HEAD)"
sudo -u "${APP_USER}" git fetch origin
remote_sha="$(sudo -u "${APP_USER}" git rev-parse origin/main)"
target_sha="${remote_sha}"
if [ "${TARGET_REF}" != "origin/main" ]; then
  target_sha="$(sudo -u "${APP_USER}" git rev-parse --verify --end-of-options "${TARGET_REF}^{commit}")"
  if [ "${MODE}" = "deploy" ] && [ "${target_sha}" != "${remote_sha}" ]; then
    echo "[update-vps] SHA non corrente: richiesto ${target_sha}, origin/main e' ${remote_sha}." >&2
    exit 1
  fi
  if [ "${MODE}" = "rollback" ] && ! sudo -u "${APP_USER}" git merge-base --is-ancestor "${target_sha}" "${remote_sha}"; then
    echo "[update-vps] rollback rifiutato: ${target_sha} non appartiene a origin/main." >&2
    exit 1
  fi
fi

if [ "${previous_sha}" = "${target_sha}" ]; then
  echo "[update-vps] gia' aggiornato (${target_sha})."
  exit 0
fi

install_revision() {
  local revision="$1"
  sudo -u "${APP_USER}" git reset --hard "${revision}"
  sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --require-hashes -r "${APP_DIR}/requirements.lock"
  sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -e "${APP_DIR}" --no-deps
  systemctl restart "${SERVICE_NAME}"
  sudo -u "${APP_USER}" bash "${APP_DIR}/deploy/smoke-check.sh"
}

if ! install_revision "${target_sha}"; then
  echo "[update-vps] deploy fallito; ripristino ${previous_sha}." >&2
  if install_revision "${previous_sha}"; then
    echo "[update-vps] rollback completato." >&2
    exit 75
  fi
  echo "[update-vps] rollback fallito: intervento manuale richiesto." >&2
  exit 1
fi

python3 - "${WEBHOOK_ENV_FILE}" <<'PY'
from pathlib import Path
import sys

env_file = Path(sys.argv[1])
if env_file.is_file():
    old = "DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT=/opt/docmolder/app/deploy/update-vps.sh"
    new = "DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT=/usr/local/sbin/docmolder-update-vps"
    lines = env_file.read_text(encoding="utf-8").splitlines()
    if old in lines:
        env_file.write_text("\n".join(new if line == old else line for line in lines) + "\n", encoding="utf-8")
PY

systemd-run \
  --quiet \
  --collect \
  --unit="docmolder-github-webhook-restart-$(date +%s)" \
  --on-active=2s \
  /bin/systemctl restart "${WEBHOOK_SERVICE}"

echo "[update-vps] deploy completato: ${target_sha}."
