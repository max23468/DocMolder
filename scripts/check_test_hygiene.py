#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TEST_COPY_RE = re.compile(r"^test.+ \d+\.py$")
COVERAGE_COPY_RE = re.compile(r"^\.coverage \d+$")


def find_hygiene_artifacts(root: Path) -> list[Path]:
    artifacts: list[Path] = []
    tests_dir = root / "tests"
    if tests_dir.exists():
        artifacts.extend(
            path
            for path in tests_dir.iterdir()
            if path.is_file() and TEST_COPY_RE.match(path.name)
        )
    artifacts.extend(
        path
        for path in root.iterdir()
        if path.is_file() and COVERAGE_COPY_RE.match(path.name)
    )
    return sorted(artifacts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect local test artifacts that can silently bloat checks or packages.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect. Defaults to the current directory.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    artifacts = find_hygiene_artifacts(root)
    if not artifacts:
        return 0

    print("Test hygiene failed: remove accidental local copies/artifacts:", file=sys.stderr)
    for path in artifacts:
        print(f"- {path.relative_to(root)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
