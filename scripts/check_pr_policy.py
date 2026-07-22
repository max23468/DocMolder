#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys


CONVENTIONAL_TITLE_RE = re.compile(
    r"^(feat|fix|deps|docs|refactor|test|chore|build|ci)(\([a-z0-9._-]+\))?!?: .+"
)
RELEASE_TITLE_RE = re.compile(r"^chore\(release\): v\d+\.\d+\.\d+$")
RELEASE_BRANCH_RE = re.compile(r"^codex/release-docmolder-\d+\.\d+\.\d+$")
RELEASE_OWNED_PATHS = frozenset(
    {
        "CHANGELOG.md",
        "pyproject.toml version",
        "src/docmolder/__init__.py",
    }
)


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n", ""}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def is_conventional_title(title: str) -> bool:
    return bool(CONVENTIONAL_TITLE_RE.match(title.strip()))


def is_release_title(title: str) -> bool:
    return bool(RELEASE_TITLE_RE.match(title.strip()))


def is_release_branch(head_ref: str) -> bool:
    return bool(RELEASE_BRANCH_RE.match(head_ref.strip()))


def check_pr_policy(
    *,
    title: str,
    head_ref: str,
    release_owned: bool,
    release_owned_files: tuple[str, ...] = (),
    changed_files: tuple[str, ...] = (),
) -> list[str]:
    errors: list[str] = []
    if not is_conventional_title(title):
        errors.append(
            "Il titolo PR deve seguire Conventional Commits, per esempio: "
            "fix(bot): handle protected PDFs more clearly"
        )

    if release_owned:
        unexpected_files = sorted(set(release_owned_files) - RELEASE_OWNED_PATHS)
        unexpected_changed_files = sorted(
            set(changed_files) - {"CHANGELOG.md", "pyproject.toml", "src/docmolder/__init__.py"}
        )
        if not release_owned_files:
            errors.append("Il diff release-owned non contiene l'elenco dei file rilevati; policy chiusa per sicurezza.")
        if not is_release_title(title) or not is_release_branch(head_ref):
            errors.append(
                "La PR tocca file release-owned (VERSIONE/CHANGELOG/manifest). "
                "Usa una branch codex/release-docmolder-X.Y.Z e il titolo chore(release): vX.Y.Z."
            )
        if unexpected_files:
            errors.append(
                "Una PR release può modificare solo i file release-owned; "
                f"file extra: {', '.join(unexpected_files)}."
            )
        if unexpected_changed_files:
            errors.append(
                "Una PR release può modificare solo CHANGELOG.md, pyproject.toml e "
                f"src/docmolder/__init__.py; file extra: {', '.join(unexpected_changed_files)}."
            )

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valida policy PR DocMolder per CI GitHub.")
    parser.add_argument("--title", required=True, help="Titolo della pull request.")
    parser.add_argument("--head-ref", required=True, help="Branch head della pull request.")
    parser.add_argument("--release-owned", type=parse_bool, required=True, help="true se il diff tocca file release-owned.")
    parser.add_argument(
        "--release-owned-files",
        default="",
        help="Lista separata da virgole dei file release-owned rilevati nel diff.",
    )
    parser.add_argument(
        "--changed-files",
        default="",
        help="Lista separata da virgole di tutti i file cambiati nel diff.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    release_owned_files = tuple(item for item in args.release_owned_files.split(",") if item)
    changed_files = tuple(item for item in args.changed_files.split(",") if item)
    errors = check_pr_policy(
        title=args.title,
        head_ref=args.head_ref,
        release_owned=args.release_owned,
        release_owned_files=release_owned_files,
        changed_files=changed_files,
    )
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    print("PR policy OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
