#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Uso: scripts/publish_change.sh '<titolo conventional commit>' [base]" >&2
  exit 2
fi

TITLE="$1"
BASE_BRANCH="${2:-main}"
BASE_REF="origin/${BASE_BRANCH}"
BRANCH="$(git branch --show-current)"
body_file=""

cleanup() {
  if [ -n "${body_file}" ] && [ -f "${body_file}" ]; then
    rm -f "${body_file}"
  fi
}
trap cleanup EXIT

if [ -z "${BRANCH}" ] || [ "${BRANCH}" = "${BASE_BRANCH}" ]; then
  python3 scripts/publish_doctor.py --base "${BASE_BRANCH}" --skip-github --fail
  bash scripts/preflight_publish.sh "${BASE_REF}"

  if [[ ! "${TITLE}" =~ ^docs(\([a-z0-9._/-]+\))?:\ [^[:space:]].+ ]]; then
    echo "Errore: il publish diretto docs-only su ${BASE_BRANCH} richiede un titolo docs: valido." >&2
    exit 1
  fi

  if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add AGENTS.md README.md docs
  fi

  if git diff --cached --quiet; then
    echo "Nessun cambio documentale da pubblicare."
    exit 0
  fi

  git commit -m "${TITLE}"
  git push origin "${BRANCH}"
  exit 0
fi

python3 scripts/publish_doctor.py --base "${BASE_BRANCH}" --fail
bash scripts/preflight_publish.sh "${BASE_REF}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -A
fi

if ! git diff --cached --quiet; then
  git commit -m "${TITLE}"
fi

git push -u origin "${BRANCH}"

body_file="$(mktemp)"
python3 scripts/generate_pr_body.py --base "${BASE_REF}" --output "${body_file}" --context "Pubblicazione automatizzata con scripts/publish_change.sh."

if [ "$(gh pr list --head "${BRANCH}" --json number --jq 'length')" = "0" ]; then
  gh pr create --draft --base "${BASE_BRANCH}" --head "${BRANCH}" --title "${TITLE}" --body-file "${body_file}"
fi
rm -f "${body_file}"
body_file=""

PR_NUMBER="$(gh pr view --json number --jq '.number')"
python3 scripts/publish_doctor.py --base "${BASE_BRANCH}" --fail
python3 scripts/check_codex_bot_comments.py --pr "${PR_NUMBER}" --fail
gh pr checks "${PR_NUMBER}" --watch --interval 10
python3 scripts/check_codex_bot_comments.py --pr "${PR_NUMBER}" --fail
gh pr ready "${PR_NUMBER}"
gh pr merge "${PR_NUMBER}" --auto --squash --delete-branch --subject "${TITLE} (#${PR_NUMBER})"
