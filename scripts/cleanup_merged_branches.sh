#!/usr/bin/env bash
set -euo pipefail

BASE_BRANCH="${1:-origin/main}"
current_branch="$(git branch --show-current)"

git fetch --prune origin

git branch --merged "${BASE_BRANCH}" \
  | sed 's/^..//' \
  | grep '^codex/' \
  | while read -r branch; do
      if [ "${branch}" = "${current_branch}" ]; then
        continue
      fi
      git branch -d "${branch}"
    done
