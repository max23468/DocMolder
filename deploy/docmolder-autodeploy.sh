#!/usr/bin/env bash
# Auto-deploy DocMolder come rete di sicurezza del webhook GitHub.
#
# Il webhook privato deploya subito a ogni push su main, ma se una consegna
# fallisce (VPS irraggiungibile, listener giu' al momento del push) quel commit
# non verrebbe mai ritentato. Questo script gira da un timer systemd: confronta
# il commit deployato (HEAD del checkout) con origin/main e, se il checkout e'
# rimasto indietro, deploya via update-vps.sh (che serializza col webhook grazie
# al lock condiviso). Se il deploy fallisce, fa ROLLBACK al commit precedente.
#
# update-vps.sh esegue git reset --hard + pip install + restart e verifica che i
# servizi siano attivi: la sua uscita non-zero e' il gate che innesca il rollback.
set -euo pipefail

APP_DIR="${DOCMOLDER_APP_DIR:-/opt/docmolder/app}"
APP_USER="${DOCMOLDER_APP_USER:-docmolder}"
BRANCH="${DOCMOLDER_DEPLOY_BRANCH:-main}"
UPDATE_SCRIPT="${APP_DIR}/deploy/update-vps.sh"

log() { echo "[autodeploy] $*"; }

cd "${APP_DIR}"
sudo -u "${APP_USER}" git config --global --add safe.directory "${APP_DIR}" >/dev/null 2>&1 || true

if ! sudo -u "${APP_USER}" git fetch origin --quiet; then
  log "git fetch fallito; riprovo al prossimo giro"
  exit 1
fi

local_sha="$(sudo -u "${APP_USER}" git rev-parse HEAD)"
remote_sha="$(sudo -u "${APP_USER}" git rev-parse "origin/${BRANCH}")"

if [ "${local_sha}" = "${remote_sha}" ]; then
  log "gia' aggiornato (${local_sha})"
  exit 0
fi

log "checkout indietro: deployato ${local_sha}, origin/${BRANCH} ${remote_sha}; deploy..."
if bash "${UPDATE_SCRIPT}" "origin/${BRANCH}"; then
  log "deploy OK -> ${remote_sha}"
  exit 0
fi

log "DEPLOY FALLITO per ${remote_sha}; rollback a ${local_sha}..." >&2
if bash "${UPDATE_SCRIPT}" "${local_sha}"; then
  log "rollback OK -> ${local_sha} (nuovo commit ${remote_sha} NON applicato)" >&2
else
  log "ROLLBACK FALLITO: intervento manuale richiesto" >&2
fi
# Uscita non-zero: l'unita' systemd risultera' 'failed', visibile in
# `systemctl --failed` e nel journal.
exit 1
