"""Utilities for safe git maintenance tasks."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def resolve_git_dir(repo_path: str = ".") -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    git_dir = result.stdout.strip()
    if not git_dir:
        raise RuntimeError("Directory git non risolta.")
    path = Path(git_dir)
    if not path.is_absolute():
        path = Path(repo_path) / path
    return path.resolve()


def list_index_lock_holders(lock_path: Path) -> list[str]:
    result = subprocess.run(
        ["lsof", str(lock_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        stderr = result.stderr.strip() or "errore sconosciuto"
        raise RuntimeError(f"Impossibile verificare i processi che tengono il lock: {stderr}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) <= 1:
        return []
    return lines[1:]


def remove_stale_index_lock(repo_path: str = ".") -> str:
    git_dir = resolve_git_dir(repo_path)
    lock_path = git_dir / "index.lock"
    if not lock_path.exists():
        return f"Nessun index.lock presente in {lock_path}."

    holders = list_index_lock_holders(lock_path)
    if holders:
        raise RuntimeError(
            "index.lock sembra ancora in uso da un processo attivo: "
            f"{holders[0]}. Non lo rimuovo automaticamente."
        )

    lock_path.unlink()
    return f"Rimosso lock Git stale: {lock_path}"


def ensure_index_lock_available(
    repo_path: str = ".",
    *,
    wait_seconds: float = 5.0,
    poll_interval: float = 0.25,
) -> list[str]:
    git_dir = resolve_git_dir(repo_path)
    lock_path = git_dir / "index.lock"
    deadline = time.monotonic() + max(0.0, wait_seconds)
    events: list[str] = []

    while lock_path.exists():
        holders = list_index_lock_holders(lock_path)
        if not holders:
            lock_path.unlink()
            events.append(f"Rimosso lock Git stale: {lock_path}")
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "index.lock ancora in uso da un processo attivo: "
                f"{holders[0]}. Riprova quando il comando Git in corso ha finito."
            )
        time.sleep(max(0.0, poll_interval))

    return events


def run_git_command(
    git_args: list[str],
    *,
    repo_path: str = ".",
    wait_seconds: float = 5.0,
    poll_interval: float = 0.25,
) -> subprocess.CompletedProcess[str]:
    ensure_index_lock_available(repo_path, wait_seconds=wait_seconds, poll_interval=poll_interval)
    return subprocess.run(
        ["git", *git_args],
        cwd=repo_path,
        check=False,
        capture_output=True,
        text=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rimuove in sicurezza un index.lock Git rimasto sporco.")
    parser.add_argument("repo", nargs="?", default=".", help="Percorso del repository Git.")
    return parser


def build_safe_git_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Esegue un comando Git aspettando o rimuovendo solo gli index.lock stale."
    )
    parser.add_argument("--repo", default=".", help="Percorso del repository Git.")
    parser.add_argument("--wait-seconds", type=float, default=5.0)
    parser.add_argument("git_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        message = remove_stale_index_lock(args.repo)
    except (subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1
    print(message)
    return 0


def safe_git_main(argv: list[str] | None = None) -> int:
    parser = build_safe_git_parser()
    args = parser.parse_args(argv)
    git_args = list(args.git_args)
    if git_args and git_args[0] == "--":
        git_args = git_args[1:]
    if not git_args:
        print("Errore: specifica un comando git da eseguire.", file=sys.stderr)
        return 2
    try:
        result = run_git_command(git_args, repo_path=args.repo, wait_seconds=args.wait_seconds)
    except RuntimeError as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        stream = sys.stderr if result.returncode else sys.stdout
        print(result.stderr, end="", file=stream)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
