#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv non disponibile: impossibile verificare requirements.lock." >&2
  exit 2
fi

lock_check_dir="$(mktemp -d)"
trap 'rm -rf "${lock_check_dir}"' EXIT

check_lock() {
  local current="$1"
  shift
  uv pip compile "$@" --universal --python-version 3.11 --generate-hashes --no-header \
    --constraint "${current}" \
    -o "${lock_check_dir}/candidate.lock" >/dev/null
  sed '/^[[:space:]]*#/d' "${current}" >"${lock_check_dir}/current.normalized"
  sed '/^[[:space:]]*#/d' "${lock_check_dir}/candidate.lock" >"${lock_check_dir}/candidate.normalized"
  if ! diff -u "${lock_check_dir}/current.normalized" "${lock_check_dir}/candidate.normalized"; then
    echo "${current} non è allineato: esegui 'make lock' e ricommitta." >&2
    exit 1
  fi
}

check_lock requirements.lock pyproject.toml
check_lock requirements-dev.lock pyproject.toml --extra dev --constraint requirements.lock
check_lock requirements-tools.lock requirements-tools.in
check_lock requirements-build.lock requirements-build.in
