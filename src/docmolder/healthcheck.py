from __future__ import annotations

import argparse
import json
import logging
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from docmolder.config import Settings
from docmolder.logging_utils import log_event
from docmolder.session_store import SQLiteSessionStore

LOGGER = logging.getLogger("docmolder.healthcheck")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _service_is_active(service_name: str) -> bool | None:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", service_name],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    return result.returncode == 0


def _sqlite_integrity_ok(database_path: Path) -> bool:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    return row is not None and row[0] == "ok"


def _directory_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for candidate in path.rglob("*"):
        if not candidate.is_file():
            continue
        try:
            total += candidate.stat().st_size
        except OSError:
            continue
    return total


def _latest_backup_age_seconds(backup_dir: Path) -> int | None:
    if not backup_dir.is_dir():
        return None
    candidates = [candidate for candidate in backup_dir.iterdir() if candidate.is_file()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
    modified_at = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
    return max(0, int((_now_utc() - modified_at).total_seconds()))


def build_health_report(
    settings: Settings,
    *,
    check_service_active: bool = False,
    service_name: str = "docmolder",
    max_queued_jobs: int | None = None,
    max_running_jobs: int | None = None,
    max_running_job_age_seconds: int | None = None,
    max_runtime_dir_bytes: int | None = None,
    max_backup_age_seconds: int | None = None,
) -> dict[str, Any]:
    runtime_dir = settings.runtime_dir
    database_path = settings.database_path
    backup_dir = settings.sqlite_backup_dir
    jobs_dir = runtime_dir / "jobs"

    reasons: list[str] = []
    warnings: list[str] = []
    alerts: list[str] = []

    runtime_exists = runtime_dir.exists()
    runtime_writable = runtime_exists and _is_writable_dir(runtime_dir)
    jobs_dir_exists = jobs_dir.exists()
    database_exists = database_path.exists()
    backup_dir_exists = backup_dir.is_dir()
    service_active = _service_is_active(service_name) if check_service_active else None

    if not runtime_exists:
        reasons.append("runtime_dir_missing")
    elif not runtime_writable:
        reasons.append("runtime_dir_not_writable")
    if not database_exists:
        reasons.append("database_missing")
    if check_service_active and service_active is False:
        alerts.append("service_inactive")

    db_integrity_ok: bool | None = None
    stats: dict[str, int] = {
        "known_users_total": 0,
        "active_sessions": 0,
        "jobs_queued": 0,
        "jobs_running": 0,
        "jobs_failed": 0,
        "jobs_succeeded": 0,
    }
    stale_running_jobs = 0
    if database_exists:
        try:
            db_integrity_ok = _sqlite_integrity_ok(database_path)
            if not db_integrity_ok:
                reasons.append("database_integrity_failed")
            store = SQLiteSessionStore(database_path)
            admin_stats = store.build_admin_stats()
            stats = {
                "known_users_total": admin_stats.known_users_total,
                "active_sessions": admin_stats.active_sessions,
                "jobs_queued": admin_stats.jobs_queued,
                "jobs_running": admin_stats.jobs_running,
                "jobs_failed": admin_stats.jobs_failed,
                "jobs_succeeded": admin_stats.jobs_succeeded,
            }
            if max_running_job_age_seconds is not None:
                stale_running_jobs = len(
                    store.list_stale_running_jobs(max_age_seconds=max_running_job_age_seconds, limit=1000)
                )
        except sqlite3.Error:
            LOGGER.exception("Healthcheck SQLite fallito.")
            reasons.append("database_unreadable")

    if max_queued_jobs is not None and stats["jobs_queued"] > max_queued_jobs:
        alerts.append("queued_jobs_exceeded")
    if max_running_jobs is not None and stats["jobs_running"] > max_running_jobs:
        alerts.append("running_jobs_exceeded")
    if max_running_job_age_seconds is not None and stale_running_jobs > 0:
        alerts.append("stale_running_jobs")

    runtime_size_bytes = _directory_size_bytes(runtime_dir)
    if max_runtime_dir_bytes is not None and runtime_size_bytes > max_runtime_dir_bytes:
        alerts.append("runtime_dir_size_exceeded")

    backup_count = len([candidate for candidate in backup_dir.iterdir() if candidate.is_file()]) if backup_dir.is_dir() else 0
    latest_backup_age_seconds = _latest_backup_age_seconds(backup_dir)
    if not backup_dir_exists:
        warnings.append("backup_dir_missing")
    elif backup_count == 0:
        warnings.append("backup_missing")
    if (
        max_backup_age_seconds is not None
        and latest_backup_age_seconds is not None
        and latest_backup_age_seconds > max_backup_age_seconds
    ):
        alerts.append("backup_stale")

    disk_usage = _disk_usage(runtime_dir if runtime_exists else runtime_dir.parent)
    status = "ok" if not reasons and not alerts else "fail"
    report: dict[str, Any] = {
        "ok": status == "ok",
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "alerts": alerts,
        "service": {
            "checked": check_service_active,
            "name": service_name if check_service_active else None,
            "active": service_active,
        },
        "runtime": {
            "dir": str(runtime_dir),
            "exists": runtime_exists,
            "writable": runtime_writable,
            "jobs_dir_exists": jobs_dir_exists,
            "size_bytes": runtime_size_bytes,
            "disk_total_bytes": disk_usage[0] if disk_usage is not None else None,
            "disk_used_bytes": disk_usage[1] if disk_usage is not None else None,
            "disk_free_bytes": disk_usage[2] if disk_usage is not None else None,
        },
        "database": {
            "path": str(database_path),
            "exists": database_exists,
            "integrity_ok": db_integrity_ok,
            "size_bytes": database_path.stat().st_size if database_exists else 0,
        },
        "backup": {
            "dir": str(backup_dir),
            "exists": backup_dir_exists,
            "count": backup_count,
            "latest_age_seconds": latest_backup_age_seconds,
        },
        "jobs": {
            **stats,
            "stale_running_jobs": stale_running_jobs,
        },
    }
    log_event(
        LOGGER,
        logging.INFO,
        "healthcheck_built",
        status=status,
        reasons_count=len(reasons),
        warnings_count=len(warnings),
        alerts_count=len(alerts),
        jobs_queued=stats["jobs_queued"],
        jobs_running=stats["jobs_running"],
    )
    return report


def render_text_report(report: dict[str, Any]) -> str:
    runtime = report["runtime"]
    database = report["database"]
    backup = report["backup"]
    jobs = report["jobs"]
    service = report["service"]
    return "\n".join(
        [
            f"status: {report['status']}",
            f"service_active: {service.get('active') if service.get('checked') else 'not_checked'}",
            f"runtime_dir: {runtime['dir']}",
            f"runtime_exists: {runtime['exists']}",
            f"runtime_writable: {runtime['writable']}",
            f"runtime_size_bytes: {runtime['size_bytes']}",
            f"database_path: {database['path']}",
            f"database_exists: {database['exists']}",
            f"database_integrity_ok: {database['integrity_ok']}",
            f"database_size_bytes: {database['size_bytes']}",
            f"backup_dir: {backup['dir']}",
            f"backup_count: {backup['count']}",
            f"backup_latest_age_seconds: {backup['latest_age_seconds']}",
            f"jobs_queued: {jobs['jobs_queued']}",
            f"jobs_running: {jobs['jobs_running']}",
            f"jobs_failed: {jobs['jobs_failed']}",
            f"jobs_succeeded: {jobs['jobs_succeeded']}",
            f"jobs_stale_running: {jobs['stale_running_jobs']}",
            "reasons: " + (", ".join(report["reasons"]) if report["reasons"] else "none"),
            "warnings: " + (", ".join(report["warnings"]) if report["warnings"] else "none"),
            "alerts: " + (", ".join(report["alerts"]) if report["alerts"] else "none"),
        ]
    )


def _disk_usage(path: Path) -> tuple[int, int, int] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return usage.total, usage.used, usage.free


def _is_writable_dir(path: Path) -> bool:
    return path.is_dir() and path.exists() and path.stat().st_mode is not None and _can_touch(path)


def _can_touch(path: Path) -> bool:
    probe = path / ".docmolder-healthcheck-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Health check operativo di DocMolder.")
    parser.add_argument("--json", action="store_true", help="Stampa il report in JSON.")
    parser.add_argument("--check-service-active", action="store_true", help="Controlla anche systemd.")
    parser.add_argument("--service-name", default="docmolder", help="Nome servizio systemd.")
    parser.add_argument("--max-queued-jobs", type=int, help="Massimo numero di job queued accettato.")
    parser.add_argument("--max-running-jobs", type=int, help="Massimo numero di job running accettato.")
    parser.add_argument("--max-running-job-age-seconds", type=int, help="Eta massima dei job running.")
    parser.add_argument("--max-runtime-dir-bytes", type=int, help="Dimensione massima runtime dir.")
    parser.add_argument("--max-backup-age-seconds", type=int, help="Eta massima ultimo backup.")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s - %(message)s", level=logging.INFO)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"settings_error: {exc}", flush=True)
        return 2

    report = build_health_report(
        settings,
        check_service_active=args.check_service_active,
        service_name=args.service_name,
        max_queued_jobs=args.max_queued_jobs if args.max_queued_jobs is not None else settings.health_max_queued_jobs,
        max_running_jobs=args.max_running_jobs if args.max_running_jobs is not None else settings.health_max_running_jobs,
        max_running_job_age_seconds=(
            args.max_running_job_age_seconds
            if args.max_running_job_age_seconds is not None
            else settings.health_max_running_job_age_seconds
        ),
        max_runtime_dir_bytes=(
            args.max_runtime_dir_bytes
            if args.max_runtime_dir_bytes is not None
            else settings.health_max_runtime_dir_bytes
        ),
        max_backup_age_seconds=(
            args.max_backup_age_seconds
            if args.max_backup_age_seconds is not None
            else settings.health_max_backup_age_seconds
        ),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
