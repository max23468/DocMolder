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
HEAD_SHA="$(git rev-parse HEAD)"

if [ -z "${BRANCH}" ] || [ "${BRANCH}" = "${BASE_BRANCH}" ]; then
  echo "Errore: crea una branch dedicata prima di pubblicare." >&2
  exit 1
fi

python3 scripts/current_failed_runs.py --branch "${BRANCH}" --sha "${HEAD_SHA}" --fail
bash scripts/preflight_publish.sh "${BASE_REF}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  git add .github deploy docs scripts src tests pyproject.toml release-please-config.json .env.example Makefile README.md AGENTS.md 2>/dev/null || true
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

PR_NUMBER="$(gh pr view --json number --jq '.number')"
gh pr checks "${PR_NUMBER}" --watch --interval 10
gh pr ready "${PR_NUMBER}"
gh pr merge "${PR_NUMBER}" --auto --squash --delete-branch --subject "${TITLE} (#${PR_NUMBER})"
