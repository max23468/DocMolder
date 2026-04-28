#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


AREA_DOCS = {
    "telegram": ["docs/TELEGRAM_OPERATIONS.md", "docs/BRAND.md"],
    "bot": ["docs/TELEGRAM_OPERATIONS.md", "docs/ARCHITECTURE.md"],
    "processing": ["docs/PDF_PIPELINE.md", "docs/ARCHITECTURE.md"],
    "pdf": ["docs/PDF_PIPELINE.md", "docs/ARCHITECTURE.md"],
    "session": ["docs/DATA_MODEL.md", "docs/ARCHITECTURE.md"],
    "sqlite": ["docs/DATA_MODEL.md", "docs/VPS_RUNBOOK.md"],
    "backup": ["docs/VPS_RUNBOOK.md", "docs/OPERATIONS_SECURITY.md"],
    "restore": ["docs/VPS_RUNBOOK.md", "docs/OPERATIONS_SECURITY.md"],
    "deploy": ["docs/VPS_RUNBOOK.md", "docs/RELEASE_PROCESS.md", "docs/VERSIONING.md"],
    "release": ["docs/RELEASE_PROCESS.md", "docs/VERSIONING.md"],
    "github": ["docs/GITHUB_ALIGNMENT.md", "docs/GITHUB_MAINTENANCE.md"],
    "docs": ["docs/INDEX.md", "docs/CONTEXT.md"],
}


def run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], check=check)


def current_branch() -> str:
    return git(["branch", "--show-current"]).stdout.strip()


def current_sha() -> str:
    return git(["rev-parse", "HEAD"], check=True).stdout.strip()


def status_short() -> str:
    return git(["status", "--short"], check=True).stdout.strip()


def recommended_docs(area: str | None) -> list[str]:
    docs = ["AGENTS.md", "docs/CONTEXT.md", "docs/DECISIONS.md", "docs/ROADMAP.md"]
    if area:
        area_lower = area.lower()
        for key, paths in AREA_DOCS.items():
            if key in area_lower:
                docs.extend(paths)
    return sorted(dict.fromkeys(docs))


def open_pr(branch: str) -> str | None:
    if not branch or shutil.which("gh") is None:
        return None
    result = run(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,title,url,isDraft",
            "--jq",
            ".[0] // empty",
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()
    draft = "draft" if data.get("isDraft") else "ready"
    return f"#{data.get('number')} {draft}: {data.get('title')} {data.get('url')}"


def print_classification(base: str) -> None:
    print("\n## Diff")
    result = run(
        [
            sys.executable,
            "scripts/classify_changes.py",
            "--base",
            base,
            "--working-tree",
        ]
    )
    if result.returncode != 0:
        print(f"- Classificazione non disponibile: {result.stderr.strip()}")
        return
    print(result.stdout.strip())


def print_failed_runs(branch: str, sha: str) -> None:
    print("\n## GitHub Actions")
    if not branch:
        print("- HEAD detached: controllo run saltato, serve --branch per current_failed_runs.py.")
        return
    result = run([sys.executable, "scripts/current_failed_runs.py", "--branch", branch, "--sha", sha])
    output = (result.stdout or result.stderr).strip()
    print(f"- {output}" if output else "- Nessun output.")


def print_parallel_safe(owner: str | None) -> None:
    print("\n## Parallel-safe")
    result = run([sys.executable, "scripts/agent_parallel_safe.py", *(["--owner", owner] if owner else [])])
    output = (result.stdout or result.stderr).strip()
    print(output or "- Nessun output.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Briefing iniziale per una sessione agente DocMolder.")
    parser.add_argument("--area", default=None, help="Area prevista, es. telegram, processing, deploy, docs.")
    parser.add_argument("--owner", default=None, help="Owner/chat corrente per i controlli parallel-safe.")
    parser.add_argument("--base", default="origin/main", help="Base per classificare il diff. Default: origin/main.")
    parser.add_argument("--skip-github", action="store_true", help="Salta controllo PR e run GitHub.")
    args = parser.parse_args()

    branch = current_branch()
    sha = current_sha()
    print(f"# Agent start: {branch or '(detached)'}@{sha[:12]}")

    status = status_short()
    print("\n## Worktree")
    print(status or "pulito")

    print("\n## Coordinamento")
    print("- Fonte unica: AGENTS.md.")
    print("- Per lavori paralleli verifica branch/PR/worktree rilevanti e segnala l'handoff in chat o PR.")

    print("\n## Documenti da leggere")
    for path in recommended_docs(args.area):
        print(f"- {path}")

    print_classification(args.base)
    print_parallel_safe(args.owner)

    if not args.skip_github:
        pr = open_pr(branch)
        print("\n## PR")
        print(f"- {pr}" if pr else "- Nessuna PR aperta rilevata per la branch corrente o gh non disponibile.")
        print_failed_runs(branch, sha)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
