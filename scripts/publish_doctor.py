#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    level: str
    message: str


def run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], check=check)


def current_branch() -> str:
    return git(["branch", "--show-current"]).stdout.strip()


def current_sha() -> str:
    return git(["rev-parse", "HEAD"], check=True).stdout.strip()


def ref_exists(ref: str) -> bool:
    return git(["rev-parse", "--verify", "--quiet", ref]).returncode == 0


def rev_counts(left: str, right: str) -> tuple[int, int]:
    result = git(["rev-list", "--left-right", "--count", f"{left}...{right}"], check=True)
    left_count, right_count = result.stdout.strip().split()
    return int(left_count), int(right_count)


def changed_files() -> list[str]:
    output = git(["status", "--porcelain"], check=True).stdout
    return [line for line in output.splitlines() if line.strip()]


def classify(base_ref: str) -> dict[str, object] | None:
    result = run(
        [
            sys.executable,
            "scripts/classify_changes.py",
            "--base",
            base_ref,
            "--working-tree",
            "--format",
            "json",
        ]
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout or "{}")


def github_available() -> bool:
    return shutil.which("gh") is not None


def gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return run(["gh", *args])


def current_failed_runs(branch: str, sha: str) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "scripts/current_failed_runs.py",
            "--branch",
            branch,
            "--sha",
            sha,
            "--fail",
        ]
    )


def open_pr_number(branch: str) -> int | None:
    result = gh(
        [
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number",
            "--jq",
            ".[0].number // empty",
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return int(result.stdout.strip())


def codex_bot_comments(pr_number: int) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            "scripts/check_codex_bot_comments.py",
            "--pr",
            str(pr_number),
            "--fail",
        ]
    )


def direct_docs_shortcut_allowed(impact: dict[str, object]) -> bool:
    paths = [str(path) for path in impact.get("changed_files", [])]
    return bool(paths) and all(path in {"AGENTS.md", "README.md"} or path.startswith("docs/") for path in paths)


def add_issue(issues: list[Issue], level: str, message: str) -> None:
    issues.append(Issue(level=level, message=message))


def collect_report(*, base_branch: str, skip_fetch: bool, skip_github: bool) -> tuple[list[Issue], dict[str, object]]:
    issues: list[Issue] = []
    details: dict[str, object] = {"base_branch": base_branch}

    branch = current_branch()
    sha = current_sha()
    details["head_sha"] = sha

    if not branch:
        add_issue(issues, "blocker", "HEAD detached: crea una branch da origin/main prima di pubblicare.")
        details["branch"] = None
        return issues, details

    details["branch"] = branch
    protected_branch = branch in {base_branch, "main", "master"}

    if not skip_fetch:
        fetch = git(["fetch", "origin", base_branch])
        if fetch.returncode != 0:
            add_issue(issues, "blocker", f"Impossibile aggiornare origin/{base_branch}: {fetch.stderr.strip()}")

    base_ref = f"origin/{base_branch}"
    details["base_ref"] = base_ref
    if not ref_exists(base_ref):
        add_issue(issues, "blocker", f"Base {base_ref} non disponibile: esegui git fetch origin {base_branch}.")
        return issues, details

    ahead, behind = rev_counts("HEAD", base_ref)
    details["ahead"] = ahead
    details["behind"] = behind
    if behind and ahead:
        add_issue(
            issues,
            "blocker",
            f"La branch diverge da {base_ref}: riallineala prima di pubblicare ({ahead} commit avanti, {behind} indietro).",
        )
    elif behind:
        add_issue(
            issues,
            "blocker",
            f"La branch e indietro di {behind} commit rispetto a {base_ref}: riparti o riallinea prima di pubblicare.",
        )

    dirty = changed_files()
    details["dirty_count"] = len(dirty)
    if dirty:
        add_issue(issues, "notice", f"Working tree con {len(dirty)} cambio/i locali: publish_change li includera nel commit.")

    impact = classify(base_ref)
    if impact is None:
        add_issue(issues, "blocker", "Classificazione diff non riuscita: controlla scripts/classify_changes.py.")
        if protected_branch:
            add_issue(issues, "blocker", f"Sei su {branch}: pubblica da una branch dedicata.")
    else:
        details["changed_count"] = impact.get("changed_count", 0)
        details["recommended_type"] = impact.get("recommended_release_type")
        details["deploy_relevant"] = impact.get("deploy_relevant")
        details["release_owned"] = impact.get("release_owned")
        details["docs_only"] = impact.get("docs_only")
        direct_docs_candidate = (
            protected_branch
            and bool(impact.get("docs_only"))
            and direct_docs_shortcut_allowed(impact)
            and not bool(impact.get("deploy_relevant"))
            and not bool(impact.get("release_owned"))
        )
        if protected_branch and direct_docs_candidate:
            add_issue(issues, "notice", "Branch principale ammessa solo per publish docs-only minuscolo.")
        elif protected_branch:
            add_issue(issues, "blocker", f"Sei su {branch}: pubblica da una branch dedicata.")
        if impact.get("release_owned"):
            files = ", ".join(str(path) for path in impact.get("release_owned_files", []))
            add_issue(
                issues,
                "blocker",
                f"Il diff tocca file riservati al flusso di release: {files}. "
                "Usa lo script manuale di rilascio per aggiornarli.",
            )
        if impact.get("deploy_relevant"):
            add_issue(issues, "notice", "Il merge attivera Deploy VPS: verifica che sia davvero atteso.")
        if not impact.get("changed_count") and not ahead:
            add_issue(issues, "notice", "Non risultano cambi da pubblicare rispetto alla base.")

    if skip_github:
        return issues, details

    if not github_available():
        add_issue(issues, "blocker", "GitHub CLI non disponibile: installa o abilita gh prima di pubblicare.")
        return issues, details

    auth = gh(["auth", "status"])
    if auth.returncode != 0:
        add_issue(issues, "blocker", "gh non è autenticato correttamente.")
        details["gh_auth_error"] = auth.stderr.strip()
        return issues, details

    failures = current_failed_runs(branch, sha)
    details["current_failed_runs_exit"] = failures.returncode
    if failures.returncode == 1:
        add_issue(issues, "blocker", "Esistono run GitHub failed per branch/SHA corrente: ispezionale prima del publish.")
    elif failures.returncode > 1:
        add_issue(issues, "blocker", "Non ho potuto leggere le run GitHub correnti: verifica lo stato prima del publish.")

    pr_number = open_pr_number(branch)
    details["open_pr"] = pr_number
    if pr_number is not None:
        bot = codex_bot_comments(pr_number)
        if bot.returncode == 1:
            add_issue(issues, "blocker", f"La PR #{pr_number} ha commenti aperti del Codex connector bot.")
        elif bot.returncode > 1:
            add_issue(issues, "notice", f"Non ho potuto leggere i commenti bot sulla PR #{pr_number}.")

    return issues, details


def print_text(issues: list[Issue], details: dict[str, object]) -> None:
    branch = details.get("branch") or "(detached)"
    sha = str(details.get("head_sha", ""))[:12]
    print(f"Publish doctor: {branch}@{sha}")
    if "ahead" in details and "behind" in details:
        print(f"Base: {details['base_ref']} | avanti: {details['ahead']} | indietro: {details['behind']}")
    if "changed_count" in details:
        print(
            "Diff: "
            f"{details['changed_count']} file, "
            f"tipo consigliato {details.get('recommended_type')}, "
            f"deploy {'sì' if details.get('deploy_relevant') else 'no'}"
        )
    blockers = [issue for issue in issues if issue.level == "blocker"]
    notices = [issue for issue in issues if issue.level == "notice"]
    if not issues:
        print("OK: nessun blocco di publish rilevato.")
        return
    for issue in blockers:
        print(f"BLOCKER: {issue.message}")
    for issue in notices:
        print(f"NOTE: {issue.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlla se la branch è pronta per il publish DocMolder.")
    parser.add_argument("--base", default="main", help="Branch base remota. Default: main.")
    parser.add_argument("--skip-fetch", action="store_true", help="Non eseguire git fetch origin <base>.")
    parser.add_argument("--skip-github", action="store_true", help="Salta controlli gh, run failed e commenti bot.")
    parser.add_argument("--json", action="store_true", help="Stampa report JSON.")
    parser.add_argument("--fail", action="store_true", help="Esci con codice 1 se ci sono blocker.")
    args = parser.parse_args()

    issues, details = collect_report(
        base_branch=args.base,
        skip_fetch=args.skip_fetch,
        skip_github=args.skip_github,
    )
    blockers = [issue for issue in issues if issue.level == "blocker"]

    if args.json:
        print(
            json.dumps(
                {
                    "details": details,
                    "issues": [issue.__dict__ for issue in issues],
                    "ok": not blockers,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_text(issues, details)

    return 1 if args.fail and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
