#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


RUN_FIELDS = (
    "databaseId,status,conclusion,headSha,headBranch,workflowName,"
    "displayTitle,event,url,createdAt"
)


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def git_value(args: list[str]) -> str:
    return run(["git", *args]).stdout.strip()


def default_branch() -> str:
    return git_value(["branch", "--show-current"])


def default_sha() -> str:
    return git_value(["rev-parse", "HEAD"])


def load_runs(branch: str, sha: str, limit: int) -> list[dict[str, object]]:
    if shutil.which("gh") is None:
        print("GitHub CLI non disponibile: salto controllo run failed correnti.", file=sys.stderr)
        return []

    result = run(
        [
            "gh",
            "run",
            "list",
            "--branch",
            branch,
            "--commit",
            sha,
            "--limit",
            str(limit),
            "--json",
            RUN_FIELDS,
        ],
        check=False,
    )
    if result.returncode != 0:
        print(f"Impossibile leggere le run GitHub correnti: {result.stderr.strip()}", file=sys.stderr)
        return []
    return json.loads(result.stdout or "[]")


def current_failures(runs: list[dict[str, object]], sha: str) -> list[dict[str, object]]:
    failures = []
    for item in runs:
        if item.get("headSha") != sha:
            continue
        if item.get("status") == "completed" and item.get("conclusion") == "failure":
            failures.append(item)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mostra solo le run GitHub Actions fallite per branch e SHA correnti."
    )
    parser.add_argument("--branch", default=None, help="Branch da controllare. Default: branch corrente.")
    parser.add_argument("--sha", default=None, help="SHA da controllare. Default: HEAD.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--fail",
        action="store_true",
        help="Esci con codice 1 se esistono failure per branch/SHA correnti.",
    )
    args = parser.parse_args()

    branch = args.branch or default_branch()
    sha = args.sha or default_sha()
    if not branch:
        print("HEAD detached: specifica --branch.", file=sys.stderr)
        return 2

    failures = current_failures(load_runs(branch, sha, args.limit), sha)
    if not failures:
        print(f"Nessuna run failed corrente per {branch}@{sha[:12]}.")
        return 0

    print(f"Run failed correnti per {branch}@{sha[:12]}:")
    for item in failures:
        name = item.get("workflowName") or item.get("displayTitle") or "workflow"
        url = item.get("url") or ""
        print(f"- {name}: {url}")
    return 1 if args.fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
