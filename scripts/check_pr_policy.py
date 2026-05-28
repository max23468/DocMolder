#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys


CONVENTIONAL_TITLE_RE = re.compile(
    r"^(feat|fix|deps|docs|refactor|test|chore|build|ci)(\([a-z0-9._-]+\))?!?: .+"
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


def check_pr_policy(*, title: str, head_ref: str, release_owned: bool) -> list[str]:
    del head_ref
    errors: list[str] = []
    if not is_conventional_title(title):
        errors.append(
            "Il titolo PR deve seguire Conventional Commits, per esempio: "
            "fix(bot): handle protected PDFs more clearly"
        )

    if release_owned:
        errors.append(
            "La PR tocca file release-owned (VERSIONE/CHANGELOG/manifest). "
            "Deve essere gestita dallo script di release manuale, non in PR funzionali."
        )

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valida policy PR DocMolder per CI GitHub.")
    parser.add_argument("--title", required=True, help="Titolo della pull request.")
    parser.add_argument("--head-ref", required=True, help="Branch head della pull request.")
    parser.add_argument("--release-owned", type=parse_bool, required=True, help="true se il diff tocca file release-owned.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    errors = check_pr_policy(title=args.title, head_ref=args.head_ref, release_owned=args.release_owned)
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        return 1

    print("PR policy OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
