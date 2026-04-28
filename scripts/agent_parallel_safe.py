#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess


def run_git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def current_branch() -> str:
    return run_git(["branch", "--show-current"]).stdout.strip()


def porcelain_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:]
        if " -> " in path:
            _old, path = path.split(" -> ", 1)
        paths.append(path.strip())
    return sorted(set(paths))


def changed_paths() -> list[str]:
    result = run_git(["status", "--porcelain"], check=True)
    return porcelain_paths(result.stdout)


def print_report(*, owner: str | None, fail_on_active: bool) -> int:
    branch = current_branch()
    paths = changed_paths()

    print(f"Parallel-safe preflight: {branch or '(detached)'}")
    if not branch:
        print("BLOCKER: HEAD detached. Crea o passa a una branch dedicata prima di lavorare.")

    if paths:
        print(f"Working tree: {len(paths)} file modificati/non tracciati.")
        for path in paths:
            print(f"- {path}")
    else:
        print("Working tree: pulito.")

    print("Coordinamento: AGENTS.md è la fonte unica; controlla branch, PR e worktree rilevanti.")
    if owner:
        print(f"Owner/chat: {owner}")
    if fail_on_active:
        print("Nota: --fail-on-active è ignorato perché non esiste più un registro agenti separato.")

    blockers = not branch

    return 1 if blockers else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlla branch e worktree prima di lavorare in parallelo.")
    parser.add_argument("--owner", default=None, help="Owner/chat corrente da mostrare nel report.")
    parser.add_argument(
        "--fail-on-active",
        action="store_true",
        help="Compatibilità legacy: non ha effetto senza registro agenti separato.",
    )
    args = parser.parse_args()
    return print_report(owner=args.owner, fail_on_active=args.fail_on_active)


if __name__ == "__main__":
    raise SystemExit(main())
