#!/usr/bin/env bash
set -euo pipefail

KEY_PATH="${HOME}/.ssh/docmolder_codex_vps"
KNOWN_HOSTS_PATH="${HOME}/.ssh/known_hosts"

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

if [[ -n "${DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64:-}" ]]; then
  printf '%s' "${DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64}" | base64 --decode > "${KEY_PATH}"
elif [[ -n "${DOCMOLDER_VPS_SSH_PRIVATE_KEY:-}" ]]; then
  printf '%s\n' "${DOCMOLDER_VPS_SSH_PRIVATE_KEY}" > "${KEY_PATH}"
else
  echo "Missing DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64 or DOCMOLDER_VPS_SSH_PRIVATE_KEY" >&2
  exit 1
fi

chmod 600 "${KEY_PATH}"

if [[ -n "${DOCMOLDER_VPS_SSH_KNOWN_HOSTS:-}" ]]; then
  touch "${KNOWN_HOSTS_PATH}"
  chmod 600 "${KNOWN_HOSTS_PATH}"
  if ! grep -Fqx "${DOCMOLDER_VPS_SSH_KNOWN_HOSTS}" "${KNOWN_HOSTS_PATH}"; then
    printf '%s\n' "${DOCMOLDER_VPS_SSH_KNOWN_HOSTS}" >> "${KNOWN_HOSTS_PATH}"
  fi
fi

echo "SSH bootstrap ready at ${KEY_PATH}"
