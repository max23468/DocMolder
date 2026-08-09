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
PUBLISH_DRAFT="${DOCMOLDER_PUBLISH_DRAFT:-0}"
PUBLISH_MERGE="${DOCMOLDER_PUBLISH_MERGE:-0}"
body_file=""

cleanup() {
  if [ -n "${body_file}" ] && [ -f "${body_file}" ]; then
    rm -f "${body_file}"
  fi
}
trap cleanup EXIT

if [ -z "${BRANCH}" ] || [ "${BRANCH}" = "${BASE_BRANCH}" ]; then
  echo "Errore: crea un branch dedicato da ${BASE_REF}; la pubblicazione passa sempre da PR." >&2
  exit 1
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
  create_args=(--base "${BASE_BRANCH}" --head "${BRANCH}" --title "${TITLE}" --body-file "${body_file}")
  if [ "${PUBLISH_DRAFT}" = "1" ]; then
    create_args=(--draft "${create_args[@]}")
  fi
  gh pr create "${create_args[@]}"
fi
rm -f "${body_file}"
body_file=""

PR_NUMBER="$(gh pr view --json number --jq '.number')"
PR_URL="$(gh pr view --json url --jq '.url')"

if [ "${PUBLISH_MERGE}" = "1" ]; then
  if [ "$(gh pr view "${PR_NUMBER}" --json isDraft --jq '.isDraft')" = "true" ]; then
    gh pr ready "${PR_NUMBER}"
  fi
  gh pr checks "${PR_NUMBER}" --watch --interval 10
  gh pr merge "${PR_NUMBER}" --squash --delete-branch --subject "${TITLE} (#${PR_NUMBER})"
  echo "PR #${PR_NUMBER} mergeata. Prossimo passo: verifica webhook VPS e deploy della modifica."
  exit 0
fi

echo "PR pronta: ${PR_URL}"
echo "Prossimo passo: self-review/merge PR; dopo il merge verifica webhook VPS e deploy della modifica."
