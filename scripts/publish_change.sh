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
USE_GH_ACTIONS="${DOCMOLDER_USE_GH_ACTIONS:-0}"
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
  python3 scripts/publish_doctor.py --base "${BASE_BRANCH}" --skip-github --fail
  bash scripts/preflight_publish.sh "${BASE_REF}"

  if [[ ! "${TITLE}" =~ ^chore(\([a-z0-9._/-]+\))?:\ [^[:space:]].+ ]]; then
    echo "Errore: il publish diretto docs-only su ${BASE_BRANCH} richiede un titolo chore: non rilasciabile." >&2
    exit 1
  fi

  if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add AGENTS.md README.md docs
  fi

  if git diff --cached --quiet; then
    ahead_count="$(git rev-list --count "${BASE_REF}..HEAD" 2>/dev/null || printf '0')"
    if [ "${ahead_count}" -gt 0 ]; then
      git push origin "${BRANCH}"
      exit 0
    fi
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
  create_args=(--base "${BASE_BRANCH}" --head "${BRANCH}" --title "${TITLE}" --body-file "${body_file}")
  if [ "${PUBLISH_DRAFT}" = "1" ] || [ "${USE_GH_ACTIONS}" = "1" ]; then
    create_args=(--draft "${create_args[@]}")
  fi
  gh pr create "${create_args[@]}"
fi
rm -f "${body_file}"
body_file=""

PR_NUMBER="$(gh pr view --json number --jq '.number')"
PR_URL="$(gh pr view --json url --jq '.url')"

if [ "${USE_GH_ACTIONS}" != "1" ]; then
  python3 scripts/check_codex_bot_comments.py --pr "${PR_NUMBER}" --fail
  if [ "${PUBLISH_MERGE}" = "1" ]; then
    if [ "$(gh pr view "${PR_NUMBER}" --json isDraft --jq '.isDraft')" = "true" ]; then
      gh pr ready "${PR_NUMBER}"
    fi
    gh pr merge "${PR_NUMBER}" --squash --delete-branch --subject "${TITLE} (#${PR_NUMBER})"
    echo "PR #${PR_NUMBER} mergeata. Prossimo passo: verifica webhook VPS, deploy e Release Please."
    exit 0
  fi
  echo "PR pronta: ${PR_URL}"
  echo "Prossimo passo: review/merge PR; dopo il merge verifica webhook VPS, deploy e Release Please."
  exit 0
fi

python3 scripts/publish_doctor.py --base "${BASE_BRANCH}" --fail
python3 scripts/check_codex_bot_comments.py --pr "${PR_NUMBER}" --fail
gh pr checks "${PR_NUMBER}" --watch --interval 10
python3 scripts/check_codex_bot_comments.py --pr "${PR_NUMBER}" --fail
if [ "$(gh pr view "${PR_NUMBER}" --json isDraft --jq '.isDraft')" = "true" ]; then
  gh pr ready "${PR_NUMBER}"
fi
gh pr merge "${PR_NUMBER}" --auto --squash --delete-branch --subject "${TITLE} (#${PR_NUMBER})"
