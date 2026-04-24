#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone


def run_git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def current_branch() -> str:
    return run_git(["branch", "--show-current"]).stdout.strip()


def current_sha() -> str:
    return run_git(["rev-parse", "HEAD"], check=True).stdout.strip()


def changed_files() -> list[str]:
    paths: set[str] = set()
    paths.update(run_git(["diff", "--name-only"], check=False).stdout.splitlines())
    paths.update(run_git(["diff", "--cached", "--name-only"], check=False).stdout.splitlines())
    paths.update(run_git(["ls-files", "--others", "--exclude-standard"], check=False).stdout.splitlines())
    return sorted(path for path in paths if path)


def split_items(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        for part in value.split(";"):
            text = part.strip()
            if text:
                items.append(text)
    return items


def print_list(title: str, items: list[str], fallback: str) -> None:
    print(f"\n## {title}")
    if not items:
        print(f"- {fallback}")
        return
    for item in items:
        print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un handoff markdown per lavori Codex/agent.")
    parser.add_argument("--owner", default="Codex", help="Owner/chat che lascia l'handoff.")
    parser.add_argument("--summary", action="append", default=[], help="Cosa e stato fatto. Ripetibile o separabile con ;")
    parser.add_argument("--check", action="append", default=[], help="Check eseguito. Ripetibile o separabile con ;")
    parser.add_argument("--risk", action="append", default=[], help="Rischio residuo. Ripetibile o separabile con ;")
    parser.add_argument("--next-step", action="append", default=[], help="Prossimo passo. Ripetibile o separabile con ;")
    parser.add_argument("--pr", default=None, help="PR collegata, se esiste.")
    args = parser.parse_args()

    branch = current_branch()
    sha = current_sha()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    files = changed_files()

    print("# Handoff agente")
    print(f"\n- Owner/chat: {args.owner}")
    print(f"- Branch/worktree: {branch or '(detached)'}")
    print(f"- SHA: {sha[:12]}")
    print(f"- Timestamp UTC: {now}")
    if args.pr:
        print(f"- PR: {args.pr}")

    print_list("Sintesi", split_items(args.summary), "Sintesi non fornita.")
    print_list("File toccati", files, "Nessun file modificato/non tracciato rilevato.")
    print_list("Check eseguiti", split_items(args.check), "Check non dichiarati.")
    print_list("Rischi residui", split_items(args.risk), "Nessun rischio residuo dichiarato.")
    print_list("Prossimo passo", split_items(args.next_step), "Prossimo passo non dichiarato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
