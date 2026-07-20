#!/usr/bin/env bash
# Configura l'aggiornamento automatico completo dell'OS via unattended-upgrades.
# Idempotente: puo' essere rieseguito senza effetti collaterali.
#
# - installa unattended-upgrades se assente;
# - abilita i job periodici apt (update lists + unattended upgrade + autoclean);
# - installa la config DocMolder (tutti gli update, cleanup kernel, auto-reboot);
# - abilita il timer apt-daily-upgrade.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="${SCRIPT_DIR}/52docmolder-unattended-upgrades"
CONF_DST="/etc/apt/apt.conf.d/52docmolder-unattended-upgrades"
PERIODIC_DST="/etc/apt/apt.conf.d/20auto-upgrades"

if [ "$(id -u)" -ne 0 ]; then
  echo "install-auto-updates.sh richiede root (usa sudo)." >&2
  exit 1
fi

if ! dpkg-query -W -f='${Status}' unattended-upgrades 2>/dev/null | grep -q "install ok installed"; then
  echo "[auto-updates] installo unattended-upgrades"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y unattended-upgrades
fi

echo "[auto-updates] scrivo ${PERIODIC_DST}"
cat > "${PERIODIC_DST}" <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

echo "[auto-updates] installo ${CONF_DST}"
install -m 644 "${CONF_SRC}" "${CONF_DST}"

echo "[auto-updates] valido la config"
unattended-upgrades --dry-run --debug >/dev/null 2>&1 || {
  echo "[auto-updates] ATTENZIONE: dry-run fallito, controllare la config" >&2
  exit 1
}

systemctl enable --now apt-daily-upgrade.timer
systemctl enable --now apt-daily.timer

echo "[auto-updates] configurato. Prossimo run:"
systemctl list-timers apt-daily-upgrade.timer --all --no-pager | grep apt-daily-upgrade || true
