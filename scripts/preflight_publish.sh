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
docs_only="$(printf '%s\n' "${impact_env}" | awk -F= '/DOCMOLDER_DOCS_ONLY=/{print $2}')"

docs_path_allowed() {
  case "$1" in
    AGENTS.md|README.md|docs/*) return 0 ;;
    *) return 1 ;;
  esac
}

main_docs_only_paths_allowed() {
  local changed_paths status path second_path
  changed_paths="$(
    {
      git diff --name-status -M "${BASE_REF}...HEAD"
      git diff --cached --name-status -M
      git diff --name-status -M
      git ls-files --others --exclude-standard | awk '{print "A\t" $0}'
    } | sort -u
  )"

  [ -n "${changed_paths}" ] || return 1

  while IFS=$'\t' read -r status path second_path; do
    case "${status}" in
      R*|C*)
        docs_path_allowed "${path}" && docs_path_allowed "${second_path}" || return 1
        ;;
      *)
        docs_path_allowed "${path}" || return 1
        ;;
    esac
  done <<< "${changed_paths}"
}

branch="$(git branch --show-current)"
if [ -z "${branch}" ]; then
  echo "Errore: HEAD detached. Crea o passa a una branch prima di pubblicare." >&2
  exit 1
fi

if [ "${branch}" = "main" ] || [ "${branch}" = "master" ]; then
  if [ "${docs_only}" = "true" ] && [ "${release_owned}" != "true" ] && main_docs_only_paths_allowed; then
    echo "Preflight: publish diretto su ${branch} ammesso per modifica documentale minuscola."
  else
    echo "Errore: sei su ${branch}. Crea una branch dedicata prima di pubblicare." >&2
    echo "Eccezione ammessa solo per cambi docs-only minuscoli limitati a AGENTS.md, README.md o docs/**." >&2
    exit 1
  fi
fi

if [ "${has_local_changes}" = "true" ]; then
  echo "Preflight: working tree non pulito, classifico anche i cambi locali."
else
  "${PYTHON_BIN}" scripts/classify_changes.py --base "${BASE_REF}"
fi

if [ "${release_owned}" = "true" ]; then
  echo "Errore: il diff tocca file riservati a release-please." >&2
  echo "Rimuovi version bump/changelog manuali oppure usa la Release PR automatica." >&2
  exit 1
fi

echo "Preflight publish OK."
