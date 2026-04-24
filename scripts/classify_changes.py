#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass


DEPLOY_RELEVANT_PATTERNS = (
    "deploy/**",
    "pyproject.toml",
    "requirements*.txt",
    "src/**",
    "uv.lock",
)

CODE_PATTERNS = (
    "src/**",
    "pyproject.toml",
    "requirements*.txt",
    "uv.lock",
)

OPS_PATTERNS = (
    ".github/workflows/deploy-vps.yml",
    ".github/workflows/update-vps-env.yml",
    "deploy/**",
    "scripts/deploy_vps_from_codex.sh",
)

DOC_PATTERNS = (
    "AGENTS.md",
    "README.md",
    "docs/**",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/**",
)

TEST_PATTERNS = (
    "tests/**",
    "scripts/smoke_telegram_desktop.py",
)

CI_PATTERNS = (
    ".github/workflows/**",
    "Makefile",
    "scripts/ci_*.sh",
    "scripts/agent_*.py",
    "scripts/codex_dev_report.py",
    "scripts/classify_changes.py",
    "scripts/current_failed_runs.py",
    "scripts/generate_pr_body.py",
    "scripts/github_maintenance_report.py",
    "scripts/ops_report.py",
    "scripts/preflight_publish.sh",
    "scripts/publish_change.sh",
    "scripts/ci_verify.sh",
)

DEPENDENCY_PATTERNS = (
    "pyproject.toml",
    "requirements*.txt",
    "uv.lock",
)

RELEASE_OWNED_FILES = {
    ".release-please-manifest.json",
    "CHANGELOG.md",
    "src/docmolder/__init__.py",
}


@dataclass(frozen=True)
class GitRange:
    base: str
    head: str


def run_git(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def ref_exists(ref: str) -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def default_base() -> str:
    for candidate in ("origin/main", "main", "HEAD~1"):
        if ref_exists(candidate):
            return candidate
    return "HEAD"


def resolve_range(base: str | None, head: str) -> GitRange:
    base_ref = base or default_base()
    if base_ref == head:
        return GitRange(base=base_ref, head=head)
    merge_base = run_git(["merge-base", base_ref, head], check=False)
    return GitRange(base=merge_base or base_ref, head=head)


def changed_files(git_range: GitRange, *, staged: bool, working_tree: bool) -> list[str]:
    paths: set[str] = set()
    if staged:
        paths.update(run_git(["diff", "--cached", "--name-only"], check=False).splitlines())
    else:
        paths.update(run_git(["diff", "--name-only", f"{git_range.base}...{git_range.head}"], check=False).splitlines())
    if working_tree:
        paths.update(run_git(["diff", "--name-only"], check=False).splitlines())
        paths.update(run_git(["ls-files", "--others", "--exclude-standard"], check=False).splitlines())
    return sorted(path for path in paths if path)


def matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def pyproject_version_changed(git_range: GitRange, paths: list[str], *, staged: bool, working_tree: bool) -> bool:
    if "pyproject.toml" not in paths:
        return False
    diff_args = ["diff", "--unified=0"]
    if staged:
        diff_args.append("--cached")
    else:
        diff_args.append(f"{git_range.base}...{git_range.head}")
    diff_args.extend(["--", "pyproject.toml"])
    diff = run_git(diff_args, check=False)
    if working_tree:
        diff += "\n" + run_git(["diff", "--unified=0", "--", "pyproject.toml"], check=False)
    version_line = re.compile(r"^[+-]\s*version\s*=")
    for line in diff.splitlines():
        if version_line.match(line):
            return True
    return False


def classify(paths: list[str], git_range: GitRange, *, staged: bool, working_tree: bool) -> dict[str, object]:
    deploy_relevant = [path for path in paths if matches(path, DEPLOY_RELEVANT_PATTERNS)]
    code = [path for path in paths if matches(path, CODE_PATTERNS)]
    ops = [path for path in paths if matches(path, OPS_PATTERNS)]
    docs = [path for path in paths if matches(path, DOC_PATTERNS)]
    tests = [path for path in paths if matches(path, TEST_PATTERNS)]
    ci = [path for path in paths if matches(path, CI_PATTERNS)]
    dependencies = [path for path in paths if matches(path, DEPENDENCY_PATTERNS)]

    release_owned = [path for path in paths if path in RELEASE_OWNED_FILES]
    if pyproject_version_changed(git_range, paths, staged=staged, working_tree=working_tree):
        release_owned.append("pyproject.toml version")

    docs_only = bool(paths) and len(docs) == len(paths)
    tests_only = bool(paths) and len(tests) == len(paths)
    ci_only = bool(paths) and len(ci) == len(paths)
    ops_only = bool(paths) and len(ops) == len(paths)
    no_runtime_impact = bool(paths) and not deploy_relevant and not code and not tests
    full_tests_required = bool(code or tests)
    package_build_required = any(path.startswith("src/") for path in code) or bool(dependencies)
    coverage_required = full_tests_required
    fast_static_required = bool(paths)
    dependency_review_required = bool(dependencies)

    return {
        "base": git_range.base,
        "head": git_range.head,
        "changed_files": paths,
        "changed_count": len(paths),
        "deploy_relevant": bool(deploy_relevant),
        "deploy_relevant_files": deploy_relevant,
        "code_relevant": bool(code),
        "code_files": code,
        "ops_relevant": bool(ops),
        "ops_files": ops,
        "docs_only": docs_only,
        "docs_files": docs,
        "tests_only": tests_only,
        "tests_files": tests,
        "ci_only": ci_only,
        "ci_files": ci,
        "dependency_relevant": bool(dependencies),
        "dependency_files": dependencies,
        "ops_only": ops_only,
        "release_owned": bool(release_owned),
        "release_owned_files": sorted(set(release_owned)),
        "no_runtime_impact": no_runtime_impact,
        "full_tests_required": full_tests_required,
        "package_build_required": package_build_required,
        "coverage_required": coverage_required,
        "fast_static_required": fast_static_required,
        "dependency_review_required": dependency_review_required,
        "recommended_deploy": bool(deploy_relevant),
        "recommended_release_type": recommended_release_type(paths, deploy_relevant, code, ops, docs_only, tests_only, ci_only),
    }


def recommended_release_type(
    paths: list[str],
    deploy_relevant: list[str],
    code: list[str],
    ops: list[str],
    docs_only: bool,
    tests_only: bool,
    ci_only: bool,
) -> str:
    if not paths:
        return "none"
    if tests_only:
        return "test"
    if ci_only and not deploy_relevant:
        return "ci"
    if docs_only:
        return "chore"
    if not code and not deploy_relevant:
        return "ci"
    if ops and not code:
        return "ci"
    return "fix"


def print_env(report: dict[str, object]) -> None:
    bool_keys = [
        "deploy_relevant",
        "code_relevant",
        "ops_relevant",
        "docs_only",
        "tests_only",
        "ci_only",
        "dependency_relevant",
        "ops_only",
        "release_owned",
        "no_runtime_impact",
        "full_tests_required",
        "package_build_required",
        "coverage_required",
        "fast_static_required",
        "dependency_review_required",
        "recommended_deploy",
    ]
    for key in bool_keys:
        print(f"DOCMOLDER_{key.upper()}={'true' if report[key] else 'false'}")
    print(f"DOCMOLDER_CHANGED_COUNT={report['changed_count']}")
    print(f"DOCMOLDER_RECOMMENDED_RELEASE_TYPE={report['recommended_release_type']}")


def print_summary(report: dict[str, object]) -> None:
    print(f"Base: {report['base']}")
    print(f"Head: {report['head']}")
    print(f"Changed files: {report['changed_count']}")
    print(f"Deploy relevant: {'yes' if report['deploy_relevant'] else 'no'}")
    print(f"Release-owned files: {'yes' if report['release_owned'] else 'no'}")
    print(f"Full tests required: {'yes' if report['full_tests_required'] else 'no'}")
    print(f"Package build required: {'yes' if report['package_build_required'] else 'no'}")
    print(f"Recommended type: {report['recommended_release_type']}")
    for path in report["changed_files"]:
        print(f"- {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classifica l'impatto dei cambi DocMolder.")
    parser.add_argument("--base", help="Ref base. Default: merge-base con origin/main/main.")
    parser.add_argument("--head", default="HEAD", help="Ref head. Default: HEAD.")
    parser.add_argument("--staged", action="store_true", help="Classifica i soli cambi staged.")
    parser.add_argument("--working-tree", action="store_true", help="Include cambi non staged.")
    parser.add_argument("--format", choices=("summary", "json", "env"), default="summary")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    git_range = resolve_range(args.base, args.head)
    paths = changed_files(git_range, staged=args.staged, working_tree=args.working_tree)
    report = classify(paths, git_range, staged=args.staged, working_tree=args.working_tree)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.format == "env":
        print_env(report)
    else:
        print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
