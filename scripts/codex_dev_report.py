#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], check=check)


def current_branch() -> str:
    return git(["branch", "--show-current"]).stdout.strip()


def current_sha() -> str:
    return git(["rev-parse", "HEAD"], check=True).stdout.strip()


def load_classification(base: str) -> dict[str, object]:
    result = run(
        [
            sys.executable,
            "scripts/classify_changes.py",
            "--base",
            base,
            "--working-tree",
            "--format",
            "json",
        ]
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip() or result.stdout.strip()}
    return json.loads(result.stdout or "{}")


def recommended_checks(report: dict[str, object]) -> list[str]:
    checks = ["git diff --check"]
    if report.get("fast_static_required"):
        checks.append("make ci-static")
    if report.get("full_tests_required"):
        checks.append("make test")
    elif report.get("docs_only") or report.get("ci_only"):
        checks.append(".venv/bin/python -m unittest discover -s tests -p 'test_agent_tools.py'")
    if report.get("package_build_required"):
        checks.append("make build")
    if report.get("deploy_relevant"):
        checks.append("make publish-doctor")
    return checks


def risk_notes(branch: str, report: dict[str, object]) -> list[str]:
    notes: list[str] = []
    if not branch:
        notes.append("HEAD detached: crea o passa a una branch dedicata prima di pubblicare.")
    if report.get("release_owned"):
        files = ", ".join(str(path) for path in report.get("release_owned_files", []))
        notes.append(f"Il diff tocca file release-owned: {files}.")
    if report.get("deploy_relevant"):
        notes.append("Diff deploy-relevant: aspettati Deploy VPS dopo merge su main.")
    if report.get("dependency_relevant"):
        notes.append("Diff dipendenze: controlla dependency review e compatibilità runtime.")
    if not report.get("changed_count"):
        notes.append("Nessun cambio rilevato rispetto alla base.")
    return notes


def print_text(branch: str, sha: str, report: dict[str, object], *, base: str) -> None:
    print(f"# Codex dev report: {branch or '(detached)'}@{sha[:12]}")
    print(f"Base: {base}")
    if "error" in report:
        print(f"BLOCKER: classificazione diff non riuscita: {report['error']}")
        return

    print("\n## Impatto")
    print(f"- File cambiati: {report.get('changed_count', 0)}")
    print(f"- Tipo consigliato: {report.get('recommended_release_type')}")
    print(f"- Deploy relevant: {'sì' if report.get('deploy_relevant') else 'no'}")
    print(f"- Runtime/code relevant: {'sì' if report.get('code_relevant') else 'no'}")
    print(f"- Release-owned: {'sì' if report.get('release_owned') else 'no'}")

    changed = report.get("changed_files", [])
    if changed:
        print("\n## File")
        for path in changed:
            print(f"- {path}")

    checks = recommended_checks(report)
    print("\n## Check consigliati")
    for command in checks:
        print(f"- `{command}`")

    notes = risk_notes(branch, report)
    print("\n## Note")
    if notes:
        for note in notes:
            print(f"- {note}")
    else:
        print("- Nessun rischio evidente dal classificatore.")

    print("\n## Prossime azioni Codex")
    print("- Usa `python3 scripts/agent_parallel_safe.py --owner <owner>` prima di editare aree condivise.")
    print("- Usa `python3 scripts/generate_pr_body.py --base <base>` prima di aprire la PR.")
    print("- Usa `python3 scripts/github_maintenance_report.py` per manutenzione/release GitHub.")
    print("- Usa `python3 scripts/ops_report.py` per osservabilità locale/VPS.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report di sviluppo Codex: diff, rischi e check consigliati.")
    parser.add_argument("--base", default="origin/main", help="Base del diff. Default: origin/main.")
    parser.add_argument("--json", action="store_true", help="Stampa JSON.")
    args = parser.parse_args()

    branch = current_branch()
    sha = current_sha()
    report = load_classification(args.base)
    payload = {
        "branch": branch,
        "sha": sha,
        "base": args.base,
        "classification": report,
        "recommended_checks": recommended_checks(report) if "error" not in report else [],
        "risk_notes": risk_notes(branch, report) if "error" not in report else [],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(branch, sha, report, base=args.base)
    return 1 if "error" in report or any("release-owned" in note for note in payload["risk_notes"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
