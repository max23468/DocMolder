#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SERVICES = (
    "docmolder.service",
    "nginx.service",
    "docmolder-db-backup.timer",
    "docmolder-alertcheck.timer",
    "docmolder-reconcile.timer",
    "docmolder-duckdns.timer",
    "certbot-renew.timer",
)


def run(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True, env=env)


def systemctl_available() -> bool:
    return shutil.which("systemctl") is not None


def service_state(name: str) -> dict[str, object]:
    if not systemctl_available():
        return {"name": name, "available": False, "active": None, "summary": "systemctl non disponibile"}
    active = run(["systemctl", "is-active", name])
    enabled = run(["systemctl", "is-enabled", name])
    return {
        "name": name,
        "available": True,
        "active": active.stdout.strip() or active.stderr.strip(),
        "enabled": enabled.stdout.strip() or enabled.stderr.strip(),
    }


def load_health(*, check_service: bool) -> tuple[dict[str, Any] | None, str | None]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    args = [
        sys.executable,
        "-m",
        "docmolder.healthcheck",
        "--json",
        "--max-running-job-age-seconds",
        "3600",
    ]
    if check_service:
        args.extend(["--check-service-active", "--service-name", "docmolder"])
    result = run(args, env=env)
    if result.returncode != 0:
        return None, result.stderr.strip() or result.stdout.strip()
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"healthcheck JSON non valido: {exc}"


def collect_report(*, check_service: bool) -> dict[str, object]:
    health, health_error = load_health(check_service=check_service)
    services = [service_state(name) for name in SERVICES]
    report: dict[str, object] = {
        "health": health,
        "health_error": health_error,
        "services": services,
        "commands": {
            "logs": "sudo journalctl -u docmolder -n 80 --no-pager",
            "health": "sudo /opt/docmolder/venv/bin/docmolder-healthcheck --check-service-active --service-name docmolder",
            "reconcile": "sudo -u docmolder /opt/docmolder/venv/bin/docmolder-reconcile",
            "smoke": "sudo /opt/docmolder/app/deploy/smoke-check.sh",
            "duckdns": "sudo /opt/docmolder/bin/update-duckdns.sh",
            "duckdns_timer": "sudo systemctl status docmolder-duckdns.timer",
            "certificates": "sudo certbot certificates",
        },
    }
    report["ok"] = health is not None and bool(health.get("ok"))
    return report


def next_actions(report: dict[str, object]) -> list[str]:
    actions: list[str] = []
    health = report.get("health")
    if not health:
        actions.append("Config/healthcheck non disponibili: verifica `.env` locale o ambiente VPS.")
        return actions
    if health.get("alerts"):
        actions.append("Alert healthcheck presenti: ispeziona log e metriche prima di deploy o merge operativo.")
    if health.get("warnings"):
        actions.append("Warning healthcheck presenti: controlla backup/runtime prima del prossimo rilascio.")
    jobs = health.get("jobs", {})
    if isinstance(jobs, dict) and jobs.get("stale_running_jobs"):
        actions.append("Job running stale: valuta `docmolder-reconcile`.")
    backup = health.get("backup", {})
    if isinstance(backup, dict) and not backup.get("count"):
        actions.append("Backup assenti: verifica timer backup o lancia backup manuale.")
    runtime = health.get("runtime", {})
    if isinstance(runtime, dict) and runtime.get("disk_free_bytes") is not None:
        free = int(runtime["disk_free_bytes"])
        total = int(runtime.get("disk_total_bytes") or 0)
        if total and free / total < 0.15:
            actions.append("Spazio disco sotto il 15 percento: pulizia runtime/log o aumento spazio.")
    system = health.get("system", {})
    if isinstance(system, dict):
        load_per_cpu = system.get("load_per_cpu_1m")
        if load_per_cpu is not None and float(load_per_cpu) > 2:
            actions.append("Load CPU alto: riduci job pesanti o verifica processi attivi sulla VPS.")
        memory_available = system.get("memory_available_bytes")
        if memory_available is not None and int(memory_available) < 128 * 1024 * 1024:
            actions.append("RAM disponibile bassa: verifica job pesanti e processi concorrenti.")
    if not actions:
        actions.append("Nessuna azione immediata dal report locale.")
    return actions


def print_text(report: dict[str, object]) -> None:
    print("# Operations report")
    health = report.get("health")
    if health:
        print("\n## Health")
        print(f"- Status: {health.get('status')}")
        print(f"- Reasons: {', '.join(health.get('reasons') or []) or 'none'}")
        print(f"- Warnings: {', '.join(health.get('warnings') or []) or 'none'}")
        print(f"- Alerts: {', '.join(health.get('alerts') or []) or 'none'}")
        jobs = health.get("jobs", {})
        if isinstance(jobs, dict):
            print(
                "- Jobs: "
                f"queued={jobs.get('jobs_queued')} running={jobs.get('jobs_running')} "
                f"failed={jobs.get('jobs_failed')} succeeded={jobs.get('jobs_succeeded')} "
                f"stale={jobs.get('stale_running_jobs')}"
            )
        system = health.get("system", {})
        if isinstance(system, dict):
            print(
                "- System: "
                f"load_per_cpu_1m={system.get('load_per_cpu_1m')} "
                f"memory_available_bytes={system.get('memory_available_bytes')}"
            )
    else:
        print("\n## Health")
        print(f"- Non disponibile: {report.get('health_error')}")

    print("\n## Systemd")
    for service in report.get("services", []):
        print(f"- {service['name']}: active={service.get('active')} enabled={service.get('enabled')}")

    print("\n## Prossime azioni")
    for action in next_actions(report):
        print(f"- {action}")

    print("\n## Comandi utili VPS")
    for label, command in report["commands"].items():
        print(f"- {label}: `{command}`")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report osservabilità/operations per DocMolder.")
    parser.add_argument("--check-service", action="store_true", help="Controlla anche systemd nel healthcheck.")
    parser.add_argument("--json", action="store_true", help="Stampa JSON.")
    args = parser.parse_args()

    report = collect_report(check_service=args.check_service)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
