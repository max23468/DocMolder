from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from docmolder.config import Settings
from docmolder.healthcheck import build_health_report
from docmolder.logging_utils import log_event
from docmolder.processing import DocumentProcessor
from docmolder.session_store import SQLiteSessionStore

LOGGER = logging.getLogger("docmolder.reconcile")


def run_reconciliation(
    settings: Settings,
    *,
    stale_running_age_seconds: int | None = None,
    prune_finished_days: int | None = None,
    prune_finished: bool = True,
    cleanup_runtime: bool = True,
) -> dict[str, Any]:
    store = SQLiteSessionStore(settings.database_path)
    processor = DocumentProcessor(
        runtime_dir=settings.runtime_dir,
        ghostscript_timeout_seconds=settings.ghostscript_timeout_seconds,
        image_pdf_max_source_side_px=settings.image_pdf_max_source_side_px,
        libreoffice_timeout_seconds=settings.libreoffice_timeout_seconds,
    )
    requeued_jobs = (
        store.requeue_stale_running_jobs(max_age_seconds=stale_running_age_seconds)
        if stale_running_age_seconds is not None
        else []
    )
    removed_job_dirs = (
        processor.cleanup_stale_job_dirs(settings.stale_job_retention_hours)
        if cleanup_runtime
        else 0
    )
    effective_prune_finished_days = None
    if prune_finished:
        effective_prune_finished_days = prune_finished_days
        if effective_prune_finished_days is None:
            effective_prune_finished_days = settings.job_history_retention_days
    pruned_finished_jobs = 0
    if effective_prune_finished_days is not None:
        pruned_finished_jobs = store.prune_finished_jobs(retention_days=effective_prune_finished_days)
        store.set_meta("reconcile:last_prune_at", datetime.now(timezone.utc).isoformat())
        store.set_meta("reconcile:last_pruned_finished_jobs", str(pruned_finished_jobs))
        store.set_meta("reconcile:last_prune_finished_days", str(effective_prune_finished_days))
    health = build_health_report(settings)
    report: dict[str, Any] = {
        "ok": True,
        "requeued_stale_running_jobs": len(requeued_jobs),
        "requeued_job_ids": [job.id for job in requeued_jobs],
        "removed_job_dirs": removed_job_dirs,
        "pruned_finished_jobs": pruned_finished_jobs,
        "prune_finished_days": effective_prune_finished_days,
        "health_status": health["status"],
        "health_warnings": health["warnings"],
    }
    log_event(
        LOGGER,
        logging.INFO,
        "reconciliation_complete",
        requeued_stale_running_jobs=len(requeued_jobs),
        removed_job_dirs=removed_job_dirs,
        pruned_finished_jobs=pruned_finished_jobs,
        prune_finished_days=effective_prune_finished_days if effective_prune_finished_days is not None else "disabled",
        health_status=health["status"],
    )
    return report


def render_text_report(report: dict[str, Any]) -> str:
    return (
        "reconciliation ok"
        f" requeued_stale_running_jobs={report['requeued_stale_running_jobs']}"
        f" removed_job_dirs={report['removed_job_dirs']}"
        f" pruned_finished_jobs={report['pruned_finished_jobs']}"
        f" prune_finished_days={report['prune_finished_days']}"
        f" health_status={report['health_status']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Riallinea job e runtime temporaneo di DocMolder.")
    parser.add_argument("--json", action="store_true", help="Stampa output JSON.")
    parser.add_argument(
        "--stale-running-age-seconds",
        type=int,
        default=3600,
        help="Requeue dei job running più vecchi di questa soglia. Usa 0 per disattivare.",
    )
    parser.add_argument(
        "--prune-finished-days",
        type=int,
        help="Rimuove job succeeded/failed più vecchi di N giorni. Se omesso usa la configurazione.",
    )
    parser.add_argument("--no-prune-finished", action="store_true", help="Disattiva pruning job conclusi per questa run.")
    parser.add_argument("--no-cleanup-runtime", action="store_true", help="Non pulire directory job stale.")
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

    stale_age = None if args.stale_running_age_seconds <= 0 else args.stale_running_age_seconds
    report = run_reconciliation(
        settings,
        stale_running_age_seconds=stale_age,
        prune_finished_days=args.prune_finished_days,
        prune_finished=not args.no_prune_finished,
        cleanup_runtime=not args.no_cleanup_runtime,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
