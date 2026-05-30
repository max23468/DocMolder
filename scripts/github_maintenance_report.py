#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from typing import Any

CODEX_INBOX_TITLE = "Codex feedback inbox"
RELEASABLE_PR_TYPES = {"feat", "fix", "deps", "docs"}


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def gh_json(args: list[str]) -> tuple[Any, str | None]:
    result = run(["gh", *args])
    if result.returncode != 0:
        return None, result.stderr.strip() or result.stdout.strip()
    try:
        return json.loads(result.stdout or "null"), None
    except json.JSONDecodeError as exc:
        return None, f"JSON gh non valido: {exc}"


def has_gh() -> bool:
    return shutil.which("gh") is not None


def current_branch() -> str:
    result = run(["git", "branch", "--show-current"])
    return result.stdout.strip()


def current_sha() -> str:
    result = run(["git", "rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else ""


def is_release_scope_pr(pr: dict[str, object]) -> bool:
    title = str(pr.get("title") or "")
    labels = pr.get("labels") or []
    if "release" in title.lower():
        return True
    if any(isinstance(label, dict) and "release" in str(label.get("name", "")).lower() for label in labels):
        return True

    match = re.match(r"^(?P<type>[A-Za-z]+)(?:\([^)]+\))?(?P<breaking>!)?:", title)
    if not match:
        return False

    pr_type = match.group("type").lower()
    return pr_type in RELEASABLE_PR_TYPES or bool(match.group("breaking"))


def collect_report(*, limit: int) -> dict[str, object]:
    report: dict[str, object] = {
        "ok": True,
        "errors": [],
        "branch": current_branch(),
        "sha": current_sha(),
    }
    errors: list[str] = []
    if not has_gh():
        report["ok"] = False
        report["errors"] = ["GitHub CLI non disponibile."]
        return report

    auth = run(["gh", "auth", "status"])
    report["gh_authenticated"] = auth.returncode == 0
    if auth.returncode != 0:
        errors.append("gh non autenticato.")

    open_prs, error = gh_json(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title,author,isDraft,headRefName,baseRefName,labels,updatedAt,url",
        ]
    )
    if error:
        errors.append(f"open PR non leggibili: {error}")
        open_prs = []
    report["open_prs"] = open_prs or []
    report["open_pr_count"] = len(report["open_prs"]) if isinstance(report["open_prs"], list) else 0

    release_prs = [
        pr
        for pr in report["open_prs"]
        if isinstance(pr, dict) and is_release_scope_pr(pr)
    ]
    report["release_prs"] = release_prs

    dependabot_prs = [
        pr
        for pr in report["open_prs"]
        if isinstance(pr, dict) and "dependabot" in str(pr.get("author", {}).get("login", "")).lower()
    ]
    report["dependabot_prs"] = dependabot_prs

    failed_runs, error = gh_json(
        [
            "run",
            "list",
            "--status",
            "failure",
            "--limit",
            str(limit),
            "--json",
            "databaseId,workflowName,displayTitle,headBranch,headSha,conclusion,status,url,createdAt",
        ]
    )
    if error:
        errors.append(f"run failed non leggibili: {error}")
        failed_runs = []
    report["failed_runs"] = failed_runs or []
    branch = str(report.get("branch") or "")
    sha = str(report.get("sha") or "")
    report["current_branch_failed_runs"] = [
        item
        for item in report["failed_runs"]
        if isinstance(item, dict) and item.get("headBranch") == branch and item.get("headSha") == sha
    ]

    inbox_issues, error = gh_json(
        [
            "issue",
            "list",
            "--search",
            f'"{CODEX_INBOX_TITLE}" in:title',
            "--state",
            "all",
            "--limit",
            "10",
            "--json",
            "number,title,state,url,updatedAt",
        ]
    )
    if error:
        errors.append(f"Codex feedback inbox non leggibile: {error}")
        inbox_issues = []
    report["codex_feedback_inbox_issues"] = inbox_issues or []
    report["codex_feedback_inbox"] = next(
        (
            issue
            for issue in report["codex_feedback_inbox_issues"]
            if isinstance(issue, dict) and issue.get("title") == CODEX_INBOX_TITLE and issue.get("state") == "OPEN"
        ),
        None,
    )

    security_alerts, error = gh_json(
        [
            "api",
            "repos/{owner}/{repo}/dependabot/alerts?state=open&per_page=20",
        ]
    )
    if error:
        report["dependabot_alerts_error"] = error
        report["dependabot_alerts"] = []
    else:
        report["dependabot_alerts"] = security_alerts or []

    report["errors"] = errors
    report["ok"] = not errors
    return report


def print_pr(pr: dict[str, object]) -> str:
    number = pr.get("number")
    title = pr.get("title")
    state = "draft" if pr.get("isDraft") else "ready"
    url = pr.get("url")
    return f"#{number} {state}: {title} ({url})"


def print_text(report: dict[str, object]) -> None:
    sha = str(report.get("sha") or "")
    suffix = f"@{sha[:12]}" if sha else ""
    print(f"# GitHub maintenance report: {report.get('branch') or '(detached)'}{suffix}")
    if report.get("errors"):
        print("\n## Errori")
        for error in report["errors"]:
            print(f"- {error}")

    print("\n## PR aperte")
    open_prs = report.get("open_prs") or []
    if open_prs:
        for pr in open_prs:
            print(f"- {print_pr(pr)}")
    else:
        print("- Nessuna PR aperta o dati non disponibili.")

    print("\n## PR da valutare per release")
    release_prs = report.get("release_prs") or []
    if release_prs:
        for pr in release_prs:
            print(f"- PR potenzialmente rilasciabile: {print_pr(pr)}")
    else:
        print("- Nessuna PR aperta potenzialmente rilasciabile rilevata.")

    print("\n## Dependabot")
    dependabot_prs = report.get("dependabot_prs") or []
    alerts = report.get("dependabot_alerts") or []
    print(f"- PR Dependabot aperte: {len(dependabot_prs)}")
    print(f"- Alert Dependabot aperti leggibili: {len(alerts)}")
    if report.get("dependabot_alerts_error"):
        print(f"- Alert non leggibili: {report['dependabot_alerts_error']}")

    print("\n## Actions failed branch/SHA corrente")
    current_failed = report.get("current_branch_failed_runs") or []
    if current_failed:
        for run_item in current_failed:
            name = run_item.get("workflowName") or run_item.get("displayTitle")
            print(f"- {name} | {run_item.get('headBranch')}@{str(run_item.get('headSha', ''))[:12]} | {run_item.get('url')}")
    else:
        print("- Nessuna run failed recente per branch e SHA corrente.")

    print("\n## Codex feedback inbox")
    inbox = report.get("codex_feedback_inbox")
    inbox_issues = report.get("codex_feedback_inbox_issues") or []
    if isinstance(inbox, dict):
        print(f"- Aperta: #{inbox.get('number')} {inbox.get('title')} ({inbox.get('url')})")
        duplicates = [
            issue
            for issue in inbox_issues
            if isinstance(issue, dict) and issue.get("title") == CODEX_INBOX_TITLE and issue.get("number") != inbox.get("number")
        ]
        if duplicates:
            print(f"- Duplicati/storici da controllare: {len(duplicates)}")
    else:
        print("- Nessuna inbox aperta rilevata; il workflow la creerà al prossimo evento utile.")

    print("\n## Actions failed recenti globali")
    failed_runs = report.get("failed_runs") or []
    if failed_runs:
        for run_item in failed_runs:
            name = run_item.get("workflowName") or run_item.get("displayTitle")
            print(f"- {name} | {run_item.get('headBranch')}@{str(run_item.get('headSha', ''))[:12]} | {run_item.get('url')}")
    else:
        print("- Nessuna run failed recente globale rilevata.")

    print("\n## Prossime azioni")
    print("- Se ci sono run failed sul branch/SHA corrente, usa `scripts/current_failed_runs.py` e `gh run view`.")
    print("- Le run globali servono per trend/manutenzione: non bloccare lavoro corrente su failure non correlate.")
    print("- Se la Codex feedback inbox segnala thread actionable, risolvili prima del merge o apri un follow-up mirato.")
    print("- Usa `scripts/check_codex_bot_comments.py --pr <numero> --fail` come guardrail sulla PR corrente.")
    print("- Se ci sono PR con scope release aperte, verifica versione/changelog prima del merge.")
    print("- Se ci sono PR Dependabot, tratta prima security update o incompatibilita runtime.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report GitHub per manutenzione, release e Actions.")
    parser.add_argument("--limit", type=int, default=20, help="Numero massimo di PR/run da leggere.")
    parser.add_argument("--json", action="store_true", help="Stampa JSON.")
    args = parser.parse_args()

    report = collect_report(limit=args.limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
