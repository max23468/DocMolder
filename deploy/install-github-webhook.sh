#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DOCMOLDER_VPS_APP_DIR:-/opt/docmolder/app}"
ENV_FILE="${DOCMOLDER_GITHUB_WEBHOOK_ENV_FILE:-/etc/docmolder/github-webhook.env}"
ENV_TEMPLATE="${APP_DIR}/deploy/github-webhook.env.example"
SERVICE_FILE="${APP_DIR}/deploy/docmolder-github-webhook.service"
WEBHOOK_SERVICE="docmolder-github-webhook.service"
WEBHOOK_RESTART_MARKER="${DOCMOLDER_GITHUB_WEBHOOK_RESTART_MARKER:-/run/docmolder-github-webhook/restart-requested}"

if [ ! -f "${ENV_TEMPLATE}" ]; then
  echo "Missing webhook env template: ${ENV_TEMPLATE}" >&2
  exit 1
fi

webhook_was_active=false
if sudo systemctl is-active --quiet "${WEBHOOK_SERVICE}" 2>/dev/null; then
  webhook_was_active=true
fi

sudo install -D -m 644 "${SERVICE_FILE}" "/etc/systemd/system/${WEBHOOK_SERVICE}"

if [ ! -f "${ENV_FILE}" ]; then
  sudo install -D -m 600 "${ENV_TEMPLATE}" "${ENV_FILE}"
fi

if sudo grep -q '^DOCMOLDER_GITHUB_WEBHOOK_SECRET=changeme$' "${ENV_FILE}" || ! sudo grep -q '^DOCMOLDER_GITHUB_WEBHOOK_SECRET=' "${ENV_FILE}"; then
  generated_secret="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  sudo python3 - <<PY
from pathlib import Path

env_file = Path("${ENV_FILE}")
lines = env_file.read_text(encoding="utf-8").splitlines()
new_lines = []
replaced = False
for line in lines:
    if line.startswith("DOCMOLDER_GITHUB_WEBHOOK_SECRET="):
        new_lines.append("DOCMOLDER_GITHUB_WEBHOOK_SECRET=${generated_secret}")
        replaced = True
    else:
        new_lines.append(line)
if not replaced:
    new_lines.append("DOCMOLDER_GITHUB_WEBHOOK_SECRET=${generated_secret}")
env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
PY
  echo "Generated DOCMOLDER_GITHUB_WEBHOOK_SECRET in ${ENV_FILE}."
fi

sudo chown root:root "${ENV_FILE}"
sudo chmod 600 "${ENV_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable --now "${WEBHOOK_SERVICE}"

if [ "${webhook_was_active}" = "true" ]; then
  if [ "${DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER:-}" = "1" ] || [ "${DOCMOLDER_GITHUB_WEBHOOK_IN_WORKER:-}" = "true" ]; then
    sudo install -d -m 755 "$(dirname "${WEBHOOK_RESTART_MARKER}")"
    printf 'requested_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | sudo tee "${WEBHOOK_RESTART_MARKER}" >/dev/null
    echo "Requested ${WEBHOOK_SERVICE} restart after current webhook job."
  else
    sudo systemctl restart "${WEBHOOK_SERVICE}"
    echo "Restarted ${WEBHOOK_SERVICE}."
  fi
fi

echo "[status]"
sudo systemctl is-active "${WEBHOOK_SERVICE}"
