#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv non disponibile: impossibile verificare requirements.lock." >&2
  exit 2
fi

lock_check_dir="$(mktemp -d)"
trap 'rm -rf "${lock_check_dir}"' EXIT

uv pip compile pyproject.toml --universal --generate-hashes --no-header \
  --constraint requirements.lock \
  -o "${lock_check_dir}/candidate.lock" >/dev/null

sed '/^[[:space:]]*#/d' requirements.lock >"${lock_check_dir}/current.normalized"
sed '/^[[:space:]]*#/d' "${lock_check_dir}/candidate.lock" >"${lock_check_dir}/candidate.normalized"

if ! diff -u "${lock_check_dir}/current.normalized" "${lock_check_dir}/candidate.normalized"; then
  echo "requirements.lock non è allineato a pyproject.toml: esegui 'make lock' e ricommitta." >&2
  exit 1
fi
