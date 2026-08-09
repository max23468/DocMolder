#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-origin/main}"
PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

has_local_changes=false
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  has_local_changes=true
fi

classify_args=(scripts/classify_changes.py --base "${BASE_REF}")
if [ "${has_local_changes}" = "true" ]; then
  classify_args+=(--working-tree)
fi

impact_env="$("${PYTHON_BIN}" "${classify_args[@]}" --format env)"
release_owned="$(printf '%s\n' "${impact_env}" | awk -F= '/DOCMOLDER_RELEASE_OWNED=/{print $2}')"
release_owned_files="$(printf '%s\n' "${impact_env}" | awk -F= '/DOCMOLDER_RELEASE_OWNED_FILES=/{print $2}')"
changed_files="$(printf '%s\n' "${impact_env}" | awk -F= '/DOCMOLDER_CHANGED_FILES=/{print $2}')"
branch="$(git branch --show-current)"
if [ -z "${branch}" ]; then
  echo "Errore: HEAD detached. Crea o passa a una branch prima di pubblicare." >&2
  exit 1
fi

if [ "${branch}" = "main" ] || [ "${branch}" = "master" ]; then
  echo "Errore: sei su ${branch}. Crea una branch dedicata prima di pubblicare." >&2
  exit 1
fi

if [ "${has_local_changes}" = "true" ]; then
  echo "Preflight: working tree non pulito, classifico anche i cambi locali."
else
  "${PYTHON_BIN}" scripts/classify_changes.py --base "${BASE_REF}"
fi

if [ "${release_owned}" = "true" ]; then
  release_version="${branch#codex/release-docmolder-}"
  "${PYTHON_BIN}" scripts/check_pr_policy.py \
    --title "chore(release): v${release_version}" \
    --head-ref "${branch}" \
    --release-owned "${release_owned}" \
    --release-owned-files "${release_owned_files}" \
    --changed-files "${changed_files}"
  echo "Preflight: scope release dedicato valido."
fi

echo "Preflight publish OK."
