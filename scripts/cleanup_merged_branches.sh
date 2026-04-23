#!/usr/bin/env bash
set -euo pipefail

BASE_BRANCH="${1:-origin/main}"
current_branch="$(git branch --show-current)"

git fetch --prune origin

git branch --merged "${BASE_BRANCH}" --format='%(refname:short)' \
  | awk '/^codex\// {print}' \
  | while read -r branch; do
      if [ "${branch}" = "${current_branch}" ]; then
        continue
      fi
      git branch -d "${branch}"
    done

git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads/codex \
  | awk '$2 == "[gone]" {print $1}' \
  | while read -r branch; do
      if [ "${branch}" = "${current_branch}" ]; then
        continue
      fi
      git branch -D "${branch}"
    done
