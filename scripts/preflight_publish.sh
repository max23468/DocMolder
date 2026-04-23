#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-origin/main}"
PYTHON_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

branch="$(git branch --show-current)"
if [ -z "${branch}" ]; then
  echo "Errore: HEAD detached. Crea o passa a una branch prima di pubblicare." >&2
  exit 1
fi

if [ "${branch}" = "main" ] || [ "${branch}" = "master" ]; then
  echo "Errore: sei su ${branch}. Crea una branch dedicata prima di pubblicare." >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Preflight: working tree non pulito, classifico anche i cambi locali."
  "${PYTHON_BIN}" scripts/classify_changes.py --base "${BASE_REF}" --working-tree
else
  "${PYTHON_BIN}" scripts/classify_changes.py --base "${BASE_REF}"
fi

release_owned="$("${PYTHON_BIN}" scripts/classify_changes.py --base "${BASE_REF}" --working-tree --format env | awk -F= '/DOCMOLDER_RELEASE_OWNED=/{print $2}')"
if [ "${release_owned}" = "true" ]; then
  echo "Errore: il diff tocca file riservati a release-please." >&2
  echo "Rimuovi version bump/changelog manuali oppure usa la Release PR automatica." >&2
  exit 1
fi

echo "Preflight publish OK."
