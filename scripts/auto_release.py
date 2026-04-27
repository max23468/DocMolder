#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


TAG_PREFIX = "docmolder-v"
RELEASE_TYPES = {"feat", "fix", "deps", "docs"}
HIDDEN_TYPES = {"chore", "ci", "test", "refactor", "build"}
SECTION_TITLES = {
    "feat": "Funzionalità",
    "fix": "Correzioni",
    "deps": "Dipendenze",
    "docs": "Documentazione",
}
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
TAG_RE = re.compile(r"^docmolder-v(\d+\.\d+\.\d+)$")
SUBJECT_RE = re.compile(
    r"^(?P<type>feat|fix|docs|deps|refactor|test|chore|build|ci)"
    r"(?:\((?P<scope>[a-z0-9._/-]+)\))?"
    r"(?P<breaking>!)?: (?P<description>.+?)(?: \(#(?P<pr>\d+)\))?$"
)
RELEASE_COMMIT_RE = re.compile(r"^chore\(main\): release docmolder \d+\.\d+\.\d+")


@dataclass(frozen=True)
class ConventionalCommit:
    sha: str
    subject: str
    body: str
    type: str
    scope: str | None
    description: str
    pr_number: str | None
    breaking: bool

    @property
    def releasable(self) -> bool:
        return self.type in RELEASE_TYPES or self.breaking


@dataclass(frozen=True)
class ReleasePlan:
    current_version: str
    next_version: str
    previous_tag: str
    next_tag: str
    commits: list[ConventionalCommit]
    changelog_entry: str


def run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=True,
    )


def git_output(args: list[str], *, cwd: Path) -> str:
    return run(["git", *args], cwd=cwd).stdout.strip()


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.match(value)
    if not match:
        raise ValueError(f"Invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def format_version(parts: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in parts)


def bump_version(current: str, bump: str) -> str:
    major, minor, patch = parse_version(current)
    if bump == "major":
        return format_version((major + 1, 0, 0))
    if bump == "minor":
        return format_version((major, minor + 1, 0))
    if bump == "patch":
        return format_version((major, minor, patch + 1))
    raise ValueError(f"Unsupported bump: {bump}")


def parse_subject(sha: str, subject: str, body: str = "") -> ConventionalCommit | None:
    if RELEASE_COMMIT_RE.match(subject):
        return None
    match = SUBJECT_RE.match(subject)
    if not match:
        return None
    commit_type = match.group("type")
    breaking = bool(match.group("breaking")) or "BREAKING CHANGE:" in body
    return ConventionalCommit(
        sha=sha,
        subject=subject,
        body=body,
        type=commit_type,
        scope=match.group("scope"),
        description=match.group("description"),
        pr_number=match.group("pr"),
        breaking=breaking,
    )


def highest_bump(commits: list[ConventionalCommit], current_version: str) -> str | None:
    if not commits:
        return None

    current_major, _, _ = parse_version(current_version)
    if any(commit.breaking for commit in commits):
        return "minor" if current_major == 0 else "major"
    if any(commit.type == "feat" for commit in commits):
        return "minor"
    if any(commit.type in {"fix", "deps", "docs"} for commit in commits):
        return "patch"
    return None


def semver_tags(*, cwd: Path) -> list[tuple[str, str]]:
    tags = git_output(["tag", "--list", f"{TAG_PREFIX}*"], cwd=cwd).splitlines()
    parsed: list[tuple[tuple[int, int, int], str, str]] = []
    for tag in tags:
        match = TAG_RE.match(tag)
        if not match:
            continue
        version = match.group(1)
        try:
            parsed.append((parse_version(version), tag, version))
        except ValueError:
            continue
    parsed.sort(reverse=True)
    return [(tag, version) for _, tag, version in parsed]


def latest_reachable_tag(*, cwd: Path) -> tuple[str, str]:
    for tag, version in semver_tags(cwd=cwd):
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", tag, "HEAD"],
            cwd=cwd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return tag, version
    raise RuntimeError(f"No reachable {TAG_PREFIX}* tag found")


def commits_since(tag: str, *, cwd: Path) -> list[ConventionalCommit]:
    output = git_output(["log", "--reverse", "--format=%H%x00%s%x00%b%x1e", f"{tag}..HEAD"], cwd=cwd)
    commits: list[ConventionalCommit] = []
    for record in output.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split("\x00", 2)
        if len(parts) != 3:
            continue
        sha, subject, body = parts
        parsed = parse_subject(sha, subject, body)
        if parsed and parsed.releasable and parsed.type not in HIDDEN_TYPES:
            commits.append(parsed)
    return commits


def github_commit_url(repository: str, sha: str) -> str:
    return f"https://github.com/{repository}/commit/{sha}"


def github_compare_url(repository: str, previous_tag: str, next_tag: str) -> str:
    return f"https://github.com/{repository}/compare/{previous_tag}...{next_tag}"


def github_issue_url(repository: str, pr_number: str) -> str:
    return f"https://github.com/{repository}/issues/{pr_number}"


def format_changelog_line(repository: str, commit: ConventionalCommit) -> str:
    scope = f"**{commit.scope}:** " if commit.scope else ""
    pr = f" ([#{commit.pr_number}]({github_issue_url(repository, commit.pr_number)}))" if commit.pr_number else ""
    short_sha = commit.sha[:7]
    return f"* {scope}{commit.description}{pr} ([{short_sha}]({github_commit_url(repository, commit.sha)}))"


def build_changelog_entry(plan: ReleasePlan, repository: str) -> str:
    lines = [
        f"## [{plan.next_version}]({github_compare_url(repository, plan.previous_tag, plan.next_tag)}) ({date.today().isoformat()})",
        "",
    ]
    for commit_type in ("feat", "fix", "deps", "docs"):
        grouped = [
            commit
            for commit in plan.commits
            if commit.type == commit_type or (commit_type == "feat" and commit.breaking and commit.type not in RELEASE_TYPES)
        ]
        if not grouped:
            continue
        lines.append("")
        lines.append(f"### {SECTION_TITLES[commit_type]}")
        lines.append("")
        for commit in grouped:
            lines.append(format_changelog_line(repository, commit))
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_release_plan(*, cwd: Path, repository: str) -> ReleasePlan | None:
    previous_tag, current_version = latest_reachable_tag(cwd=cwd)
    commits = commits_since(previous_tag, cwd=cwd)
    bump = highest_bump(commits, current_version)
    if bump is None:
        return None
    next_version = bump_version(current_version, bump)
    next_tag = f"{TAG_PREFIX}{next_version}"
    plan = ReleasePlan(
        current_version=current_version,
        next_version=next_version,
        previous_tag=previous_tag,
        next_tag=next_tag,
        commits=commits,
        changelog_entry="",
    )
    return ReleasePlan(
        current_version=plan.current_version,
        next_version=plan.next_version,
        previous_tag=plan.previous_tag,
        next_tag=plan.next_tag,
        commits=plan.commits,
        changelog_entry=build_changelog_entry(plan, repository),
    )


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one replacement in {path}")
    path.write_text(new_text, encoding="utf-8")


def update_changelog(path: Path, entry: str) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^## \[", text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find first release heading in CHANGELOG.md")
    new_text = text[: match.start()] + entry + "\n" + text[match.start() :]
    path.write_text(new_text, encoding="utf-8")


def update_release_files(*, cwd: Path, plan: ReleasePlan) -> None:
    update_changelog(cwd / "CHANGELOG.md", plan.changelog_entry)
    replace_once(cwd / "pyproject.toml", r'^version = "[^"]+"$', f'version = "{plan.next_version}"')
    replace_once(cwd / "src/docmolder/__init__.py", r'^__version__ = "[^"]+"$', f'__version__ = "{plan.next_version}"')
    manifest_path = cwd / ".release-please-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["."] = plan.next_version
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ensure_clean(*, cwd: Path) -> None:
    status = git_output(["status", "--porcelain"], cwd=cwd)
    if status:
        raise RuntimeError("Working tree is not clean; refusing to auto-release")


def tag_exists(tag: str, *, cwd: Path) -> bool:
    result = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"], cwd=cwd, check=False)
    return result.returncode == 0


def configure_git_identity(*, cwd: Path, name: str, email: str) -> None:
    run(["git", "config", "user.name", name], cwd=cwd)
    run(["git", "config", "user.email", email], cwd=cwd)


def write_askpass(token: str) -> tempfile.TemporaryDirectory[str]:
    tempdir = tempfile.TemporaryDirectory(prefix="docmolder-release-")
    script = Path(tempdir.name) / "askpass.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$1\" in\n"
        "  *Username*) printf '%s\\n' 'x-access-token' ;;\n"
        f"  *Password*) printf '%s\\n' {json.dumps(token)} ;;\n"
        "  *) printf '%s\\n' '' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return tempdir


def push_with_token(*, cwd: Path, repository: str, branch: str, tag: str, token: str) -> None:
    with write_askpass(token) as tempdir:
        env = os.environ.copy()
        env["GIT_ASKPASS"] = str(Path(tempdir) / "askpass.sh")
        env["GIT_TERMINAL_PROMPT"] = "0"
        remote_url = f"https://github.com/{repository}.git"
        run(["git", "push", remote_url, f"HEAD:{branch}"], cwd=cwd, env=env)
        run(["git", "push", remote_url, f"refs/tags/{tag}:refs/tags/{tag}"], cwd=cwd, env=env)


def github_request(method: str, path: str, *, token: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def release_body(plan: ReleasePlan) -> str:
    lines = plan.changelog_entry.splitlines()
    # Drop the release heading; GitHub already shows tag and title.
    return "\n".join(lines[2:]).strip() + "\n"


def ensure_github_release(*, repository: str, token: str, plan: ReleasePlan) -> None:
    status, existing = github_request("GET", f"/repos/{repository}/releases/tags/{plan.next_tag}", token=token)
    payload = {
        "tag_name": plan.next_tag,
        "target_commitish": "main",
        "name": f"docmolder {plan.next_version}",
        "body": release_body(plan),
        "draft": False,
        "prerelease": False,
    }
    if status == 200 and isinstance(existing, dict):
        release_id = existing["id"]
        update_status, update_response = github_request("PATCH", f"/repos/{repository}/releases/{release_id}", token=token, payload=payload)
        if update_status not in {200}:
            raise RuntimeError(f"GitHub release update failed: {update_status} {update_response}")
        return
    if status != 404:
        raise RuntimeError(f"GitHub release lookup failed: {status} {existing}")

    create_status, create_response = github_request("POST", f"/repos/{repository}/releases", token=token, payload=payload)
    if create_status not in {200, 201}:
        raise RuntimeError(f"GitHub release creation failed: {create_status} {create_response}")


def apply_release(*, cwd: Path, repository: str, branch: str, token: str, author_name: str, author_email: str, dry_run: bool) -> str:
    run(["git", "fetch", "--tags", "origin", branch], cwd=cwd)
    ensure_clean(cwd=cwd)
    plan = build_release_plan(cwd=cwd, repository=repository)
    if plan is None:
        return "No releasable commits since latest release tag."

    if tag_exists(plan.next_tag, cwd=cwd):
        if dry_run:
            return f"Would ensure GitHub release for existing tag {plan.next_tag}."
        ensure_github_release(repository=repository, token=token, plan=plan)
        return f"Release {plan.next_tag} already tagged; GitHub release ensured."

    if dry_run:
        return f"Would release {plan.next_tag} from {plan.previous_tag}."

    update_release_files(cwd=cwd, plan=plan)
    configure_git_identity(cwd=cwd, name=author_name, email=author_email)
    run(["git", "add", "CHANGELOG.md", ".release-please-manifest.json", "pyproject.toml", "src/docmolder/__init__.py"], cwd=cwd)
    run(["git", "commit", "-m", f"chore(main): release docmolder {plan.next_version}"], cwd=cwd)
    run(["git", "tag", plan.next_tag], cwd=cwd)
    push_with_token(cwd=cwd, repository=repository, branch=branch, tag=plan.next_tag, token=token)
    ensure_github_release(repository=repository, token=token, plan=plan)
    return f"Released {plan.next_tag}."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create DocMolder release commits, tags, and GitHub Releases without GitHub Actions.")
    parser.add_argument("--repo-dir", default=".", help="Repository directory.")
    parser.add_argument("--repository", default=os.getenv("DOCMOLDER_RELEASE_REPOSITORY", "max23468/DocMolder"))
    parser.add_argument("--branch", default=os.getenv("DOCMOLDER_RELEASE_BRANCH", "main"))
    parser.add_argument("--token-env", default="DOCMOLDER_RELEASE_GITHUB_TOKEN")
    parser.add_argument("--author-name", default=os.getenv("DOCMOLDER_RELEASE_GIT_AUTHOR_NAME", "docmolder-release-bot"))
    parser.add_argument("--author-email", default=os.getenv("DOCMOLDER_RELEASE_GIT_AUTHOR_EMAIL", "docmolder-release-bot@users.noreply.github.com"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.getenv(args.token_env, "").strip()
    if not token and not args.dry_run:
        print(f"Missing {args.token_env}; cannot push release commit or create GitHub Release.", file=sys.stderr)
        return 2
    try:
        message = apply_release(
            cwd=Path(args.repo_dir).resolve(),
            repository=args.repository,
            branch=args.branch,
            token=token,
            author_name=args.author_name,
            author_email=args.author_email,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"auto-release failed: {exc}", file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
