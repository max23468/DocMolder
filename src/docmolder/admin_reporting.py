from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo

from telegram.error import TelegramError
from telegram.ext import Application

from docmolder.access_control import (
    ACCESS_STATUS_PENDING as _ACCESS_STATUS_PENDING,
    list_dynamic_access_statuses as _list_dynamic_access_statuses,
)
from docmolder.healthcheck import build_health_report
from docmolder.models import AdminActionStat, AdminStats, AdminUserStat, JobRecord, JobStatus
import docmolder.bot_results as bot_results
import docmolder.bot_runtime as bot_runtime


class AdminAlertPayload(TypedDict):
    key: str
    signature: str
    text: str


def _is_periodic_admin_report_enabled(deps: bot_runtime.BotDependencies, period: str) -> bool:
    return deps.session_store.get_meta(f"admin_report_{period}_enabled") != "0"


def _set_periodic_admin_report_enabled(
    deps: bot_runtime.BotDependencies, period: str, enabled: bool, *, now: datetime | None = None
) -> None:
    deps.session_store.set_meta(f"admin_report_{period}_enabled", "1" if enabled else "0")
    if enabled:
        current = now or datetime.now(ZoneInfo("Europe/Rome"))
        report_is_already_due = (
            period == "daily" and current.hour >= deps.settings.admin_daily_report_hour
        ) or (
            period == "weekly"
            and current.weekday() == deps.settings.admin_weekly_report_day
            and current.hour >= deps.settings.admin_weekly_report_hour
        )
        if report_is_already_due:
            deps.session_store.set_meta(f"admin_report_{period}_last_sent", current.date().isoformat())


def _build_admin_report(
    stats: AdminStats,
    top_users: list[AdminUserStat],
    failed_actions: list[AdminActionStat],
    recent_failed_jobs: list[JobRecord],
    recent_completed_jobs: list[JobRecord],
    slow_jobs: list[JobRecord] | None = None,
    *,
    activity_window_label: str = "ultimi 7 giorni",
    completed_jobs_heading: str = "Ultimi job completati",
    failed_jobs_heading: str = "Ultimi job falliti",
    slow_jobs_heading: str = "Job lenti ultime 24 ore",
) -> str:
    timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M")
    total_finished_jobs = stats.jobs_succeeded + stats.jobs_failed
    success_rate = bot_results._format_percent(stats.jobs_succeeded, total_finished_jobs)
    failure_rate = bot_results._format_percent(stats.jobs_failed, total_finished_jobs)
    failure_rate_24h = bot_results._format_percent(stats.jobs_failed_last_24h, stats.jobs_finished_last_24h)
    raster_share = bot_results._format_percent(stats.raster_results_total, stats.jobs_succeeded)
    top_users_block = (
        "\n".join((f"- {entry.label} ({entry.user_id}): {entry.completed_actions} operazioni" for entry in top_users))
        or "- Nessun dato ancora disponibile"
    )
    failed_actions_block = (
        "\n".join((f"- {bot_results._action_label(entry.action)}: {entry.total}" for entry in failed_actions))
        or "- Nessun pattern di errore rilevante"
    )
    failed_jobs_block = (
        "\n".join((bot_results._format_job_line(job) for job in recent_failed_jobs))
        or "- Nessun job fallito di recente"
    )
    completed_jobs_block = (
        "\n".join((bot_results._format_job_line(job) for job in recent_completed_jobs))
        or "- Nessun job completato di recente"
    )
    slow_jobs_block = (
        "\n".join((bot_results._format_job_line(job) for job in slow_jobs or [])) or "- Nessun job lento rilevante"
    )
    return f"Riepilogo admin DocMolder\nAggiornato: {timestamp}\n\nUtenti unici totali: {stats.known_users_total}\nNuovi utenti ultime 24 ore: {stats.known_users_last_24h}\nNuovi utenti ultimi 7 giorni: {stats.known_users_last_7d}\nUtenti attivi ultime 24 ore: {stats.active_users_last_24h}\nUtenti attivi ultimi 7 giorni: {stats.active_users_last_7d}\nOperazioni completate totali: {stats.completed_actions_total}\nOperazioni completate ultime 24 ore: {stats.completed_actions_last_24h}\nOperazioni completate ultimi 7 giorni: {stats.completed_actions_last_7d}\nSessioni attive ora: {stats.active_sessions}\n\nStato coda:\n- In coda: {stats.jobs_queued}\n- In lavorazione: {stats.jobs_running}\n- Falliti: {stats.jobs_failed}\n- Completati: {stats.jobs_succeeded}\n\nMetriche tecniche medie:\n- Durata: {bot_results._format_duration_ms(stats.avg_duration_ms)}\n- Input: {bot_results._format_bytes(stats.avg_input_bytes)}\n- Output: {bot_results._format_bytes(stats.avg_output_bytes)}\n- Risultati con fallback raster: {stats.raster_results_total} ({raster_share})\n\nSintesi qualità:\n- Job riusciti: {stats.jobs_succeeded} ({success_rate})\n- Job falliti: {stats.jobs_failed} ({failure_rate})\n\nFinestra ultime 24 ore:\n- Job conclusi: {stats.jobs_finished_last_24h}\n- Job falliti: {stats.jobs_failed_last_24h} ({failure_rate_24h})\n\nDettaglio operazioni:\n- PDF da immagini: {stats.images_to_pdf_total}\n- Comprimi PDF: {stats.pdf_compress_total}\n- Scala di grigi: {stats.pdf_grayscale_total}\n- Unisci PDF: {stats.pdf_merge_total}\n- Dividi PDF: {stats.pdf_split_total}\n- Estrai pagine: {stats.pdf_extract_pages_total}\n- Riordina pagine: {stats.pdf_reorder_pages_total}\n- Elimina pagine: {stats.pdf_delete_pages_total}\n- Ruota pagine: {stats.pdf_rotate_total}\n- Watermark: {stats.pdf_watermark_total}\n- Correggi orientamento: {stats.auto_orient_total}\n\nErrori più frequenti {activity_window_label}:\n{failed_actions_block}\n\nUtenti più attivi {activity_window_label}:\n{top_users_block}\n\n{completed_jobs_heading}:\n{completed_jobs_block}\n\n{slow_jobs_heading}:\n{slow_jobs_block}\n\n{failed_jobs_heading}:\n{failed_jobs_block}"


def _list_recent_slow_jobs(
    deps: bot_runtime.BotDependencies, *, since_days: int = 1, limit: int = 5
) -> list[JobRecord]:
    threshold_ms = max(1, int(deps.settings.admin_slow_job_threshold_ms))
    candidates = deps.session_store.list_recent_jobs(limit=200, statuses=(JobStatus.SUCCEEDED,), since_days=since_days)
    slow_jobs = [job for job in candidates if (job.duration_ms or 0) >= threshold_ms]
    slow_jobs.sort(key=lambda job: (job.duration_ms or 0, job.finished_at or job.created_at, job.id), reverse=True)
    return slow_jobs[:limit]


def _build_admin_queue_report(deps: bot_runtime.BotDependencies) -> str:
    stats = deps.session_store.build_admin_stats()
    queued_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.QUEUED,))
    running_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.RUNNING,))
    recent_failed_jobs = deps.session_store.list_recent_jobs(limit=3, statuses=(JobStatus.FAILED,))
    recent_failed_actions = deps.session_store.list_failed_actions(
        limit=3, since_minutes=max(5, deps.settings.admin_alert_window_minutes)
    )
    queue_backlog = deps.job_queue.qsize()
    queued_block = (
        "\n".join((bot_results._format_job_line(job) for job in queued_jobs)) or "- Nessun job in coda persistente"
    )
    running_block = (
        "\n".join((bot_results._format_job_line(job) for job in running_jobs)) or "- Nessun job in esecuzione"
    )
    failed_block = (
        "\n".join((bot_results._format_job_line(job) for job in recent_failed_jobs)) or "- Nessun job fallito recente"
    )
    failed_actions_block = (
        "\n".join((f"- {bot_results._action_label(entry.action)}: {entry.total}" for entry in recent_failed_actions))
        or "- Nessun pattern di errore recente"
    )
    return f"Coda operativa DocMolder\n- Service mode: {bot_runtime._build_service_status_label(deps)}\n- Coda in memoria: {queue_backlog}\n- Job queued persistiti: {stats.jobs_queued}\n- Job running persistiti: {stats.jobs_running}\n- Job conclusi ultime 24 ore: {stats.jobs_finished_last_24h}\n- Failure rate 24h: {bot_results._format_percent(stats.jobs_failed_last_24h, stats.jobs_finished_last_24h)}\n- Sessioni attive: {stats.active_sessions}\n\nUltimi job in coda:\n{queued_block}\n\nJob in lavorazione:\n{running_block}\n\nUltimi job falliti:\n{failed_block}\n\nErrori ricorrenti recenti:\n{failed_actions_block}"


def _build_admin_health_report(deps: bot_runtime.BotDependencies) -> str:
    settings = deps.settings
    runtime_dir = settings.runtime_dir
    database_path = settings.database_path
    backup_dir = getattr(settings, "sqlite_backup_dir", runtime_dir / "backups")
    runtime_status = "ok" if runtime_dir.exists() else "mancante"
    db_status = "ok" if database_path.exists() else "mancante"
    backup_status = "ok" if backup_dir.exists() else "mancante"
    db_size = bot_results._format_bytes(database_path.stat().st_size) if database_path.exists() else "0 B"
    stats = deps.session_store.build_admin_stats()
    failure_rate_24h = bot_results._format_percent(stats.jobs_failed_last_24h, stats.jobs_finished_last_24h)
    backup_count = len(list(backup_dir.glob("*"))) if backup_dir.exists() else 0
    disk_snapshot = bot_runtime._runtime_disk_snapshot(runtime_dir)
    disk_block = (
        f"- Disco totale: {bot_results._format_bytes(disk_snapshot[0])}\n- Disco usato: {bot_results._format_bytes(disk_snapshot[1])}\n- Disco libero: {bot_results._format_bytes(disk_snapshot[2])}"
        if disk_snapshot is not None
        else "- Disco: non disponibile"
    )
    worker_status = "attivo" if deps.job_worker_task is not None and (not deps.job_worker_task.done()) else "fermato"
    cleanup_status = "attivo" if deps.cleanup_task is not None and (not deps.cleanup_task.done()) else "fermato"
    admin_status = "attivo" if deps.admin_report_task is not None and (not deps.admin_report_task.done()) else "fermato"
    return f"Health operativo DocMolder\n- Service mode: {bot_runtime._build_service_status_label(deps)}\n- Runtime dir: {runtime_dir} ({runtime_status})\n- Database SQLite: {database_path} ({db_status}, {db_size})\n- Backup dir: {backup_dir} ({backup_status}, {backup_count} file)\n- Worker job: {worker_status}\n- Cleanup schedulato: {cleanup_status}\n- Report admin schedulati: {admin_status}\n- Coda in memoria: {deps.job_queue.qsize()}\n- Utenti attivi 24h/7g: {stats.active_users_last_24h}/{stats.active_users_last_7d}\n- Job conclusi 24h: {stats.jobs_finished_last_24h}\n- Failure rate 24h: {failure_rate_24h}\n{disk_block}"


def _build_admin_maintenance_overview(deps: bot_runtime.BotDependencies) -> str:
    max_running_age_seconds = int(getattr(deps.settings, "health_max_running_job_age_seconds", 3600))
    health = build_health_report(
        deps.settings,
        max_queued_jobs=getattr(deps.settings, "health_max_queued_jobs", 20),
        max_running_jobs=getattr(deps.settings, "health_max_running_jobs", 5),
        max_running_job_age_seconds=max_running_age_seconds,
        max_runtime_dir_bytes=getattr(deps.settings, "health_max_runtime_dir_bytes", 2147483648),
        max_database_bytes=getattr(deps.settings, "health_max_database_bytes", 134217728),
        max_backup_age_seconds=getattr(deps.settings, "health_max_backup_age_seconds", 172800),
        max_finished_jobs_24h=getattr(deps.settings, "health_max_finished_jobs_24h", 300),
        max_active_users_7d=getattr(deps.settings, "health_max_active_users_7d", 100),
        max_failure_rate_percent=getattr(deps.settings, "health_max_failure_rate_percent", 40),
        failure_rate_min_finished_jobs=getattr(deps.settings, "health_failure_rate_min_finished_jobs", 10),
    )
    stale_jobs = deps.session_store.list_stale_running_jobs(max_age_seconds=max_running_age_seconds, limit=5)
    stats = deps.session_store.build_admin_stats()
    pending_users = [
        user_id for user_id, status in _list_dynamic_access_statuses(deps) if status == _ACCESS_STATUS_PENDING
    ]
    recent_audit_entries = deps.session_store.list_audit_log_entries(limit=5)
    deletion_count = sum((1 for entry in recent_audit_entries if entry.event_type == "user_data_deleted"))
    last_prune_at = deps.session_store.get_meta("reconcile:last_prune_at") or "mai registrato"
    last_pruned_jobs = deps.session_store.get_meta("reconcile:last_pruned_finished_jobs") or "0"
    last_prune_days = deps.session_store.get_meta("reconcile:last_prune_finished_days") or "disabled"
    growth_alerts = _build_growth_guardrail_messages(deps, stats)
    stale_block = "\n".join((bot_results._format_job_line(job) for job in stale_jobs)) or "- Nessun running stale"
    pending_block = "\n".join((f"- Utente {user_id}" for user_id in pending_users[:5])) or "- Nessuna richiesta pending"
    audit_block = (
        "\n".join(
            (
                f"- {entry.event_type}: {entry.outcome} ({entry.actor_user_id or 'sistema'} -> {entry.target_user_id or '-'})"
                for entry in recent_audit_entries
            )
        )
        or "- Nessun evento audit"
    )
    growth_block = "\n".join((f"- {message}" for message in growth_alerts)) or "- Nessuna soglia prudenziale superata"
    alerts = ", ".join(health.get("alerts", [])) or "nessun alert"
    warnings = ", ".join(health.get("warnings", [])) or "nessun warning"
    return f"Manutenzione operativa DocMolder\n- Health: {health['status']}\n- Alert: {alerts}\n- Warning: {warnings}\n- Runtime size: {bot_results._format_bytes(int(health['runtime']['size_bytes']))}\n- Database size: {bot_results._format_bytes(int(health['database']['size_bytes']))}\n- Backup disponibili: {health['backup']['count']}\n- Ultimo backup age seconds: {health['backup']['latest_age_seconds']}\n- Ultimo pruning job: {last_pruned_jobs} job, retention {last_prune_days}, at {last_prune_at}\n- Cancellazioni dati recenti: {deletion_count}\n\nSoglie crescita prudente:\n{growth_block}\n\nRunning stale:\n{stale_block}\n\nRichieste accesso pending:\n{pending_block}\n\nAudit recente:\n{audit_block}"


def _build_growth_guardrail_messages(deps: bot_runtime.BotDependencies, stats: AdminStats) -> list[str]:
    settings = deps.settings
    messages: list[str] = []
    if stats.jobs_finished_last_24h > settings.health_max_finished_jobs_24h:
        messages.append(
            f"job/giorno {stats.jobs_finished_last_24h}>{settings.health_max_finished_jobs_24h}: valuta manutenzione o allow-list"
        )
    if stats.active_users_last_7d > settings.health_max_active_users_7d:
        messages.append(
            f"utenti attivi 7g {stats.active_users_last_7d}>{settings.health_max_active_users_7d}: rivaluta VPS singola"
        )
    if stats.jobs_finished_last_24h >= settings.health_failure_rate_min_finished_jobs:
        failure_rate = _percent_int(stats.jobs_failed_last_24h, stats.jobs_finished_last_24h)
        if failure_rate > settings.health_max_failure_rate_percent:
            messages.append(
                f"failure rate 24h {failure_rate}%>{settings.health_max_failure_rate_percent}%: controlla errori recenti"
            )
    database_path = settings.database_path
    if database_path.exists() and database_path.stat().st_size > settings.health_max_database_bytes:
        messages.append(
            f"database {bot_results._format_bytes(database_path.stat().st_size)}>{bot_results._format_bytes(settings.health_max_database_bytes)}: valuta pruning o backup"
        )
    if stats.jobs_queued > settings.health_max_queued_jobs:
        messages.append(f"coda {stats.jobs_queued}>{settings.health_max_queued_jobs}: valuta pausa temporanea")
    return messages


def _percent_int(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return round(numerator / denominator * 100)


def _extract_metric_entries(raw_meta: dict[str, str], prefix: str) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for key, raw_value in raw_meta.items():
        if not key.startswith(prefix):
            continue
        try:
            value = int(raw_value)
        except ValueError:
            continue
        entries.append((key.removeprefix(prefix), value))
    entries.sort(key=lambda item: (-item[1], item[0]))
    return entries


def _format_upload_metric_name(name: str) -> str:
    return {"photo": "foto", "document": "documenti"}.get(name, name)


def _build_telegram_metrics_report(deps: bot_runtime.BotDependencies) -> str:
    raw_meta = deps.session_store.list_meta(bot_runtime._TELEGRAM_METRIC_PREFIX)
    command_entries = _extract_metric_entries(raw_meta, f"{bot_runtime._TELEGRAM_METRIC_PREFIX}command:")
    callback_entries = _extract_metric_entries(raw_meta, f"{bot_runtime._TELEGRAM_METRIC_PREFIX}callback:")
    upload_entries = _extract_metric_entries(raw_meta, f"{bot_runtime._TELEGRAM_METRIC_PREFIX}upload:")
    command_block = (
        "\n".join((f"- /{name}: {count}" for name, count in command_entries)) or "- Nessun comando registrato ancora"
    )
    callback_block = (
        "\n".join((f"- {name}: {count}" for name, count in callback_entries[:8]))
        or "- Nessuna callback rilevata ancora"
    )
    upload_block = (
        "\n".join((f"- {_format_upload_metric_name(name)}: {count}" for name, count in upload_entries))
        or "- Nessun upload registrato ancora"
    )
    flow_counts = deps.session_store.count_flow_events(since_days=7)
    started_flows = flow_counts.get("upload", 0)
    selected_flows = flow_counts.get("action_selected", 0)
    queued_flows = flow_counts.get("queued", 0)
    succeeded_flows = flow_counts.get("succeeded", 0)
    failed_flows = flow_counts.get("failed", 0)
    flow_block = (
        f"- Flussi avviati: {started_flows}\n"
        f"- Con azione scelta: {selected_flows} ({bot_results._format_percent(selected_flows, started_flows)})\n"
        f"- Accodati: {queued_flows} ({bot_results._format_percent(queued_flows, selected_flows)})\n"
        f"- Riusciti: {succeeded_flows}\n"
        f"- Falliti: {failed_flows}\n"
        f"- Interrotti prima della scelta: {max(0, started_flows - selected_flows)}\n"
        f"- Interrotti tra scelta e coda: {max(0, selected_flows - queued_flows)}\n"
        f"- Procedure annullate: {flow_counts.get('cancelled', 0)}\n"
        f"- Nuovi lavori avviati: {flow_counts.get('reset', 0)}"
    )
    return f"Metriche Telegram DocMolder\nComandi:\n{command_block}\n\nUpload:\n{upload_block}\n\nFunnel ultimi 7 giorni (solo metadati tecnici):\n{flow_block}\n\nRetry Telegram:\n- sendMessage rate limit: {bot_runtime._get_meta_counter(deps, f'{bot_runtime._TELEGRAM_METRIC_PREFIX}retry_after:sendMessage')}\n- sendDocument rate limit: {bot_runtime._get_meta_counter(deps, f'{bot_runtime._TELEGRAM_METRIC_PREFIX}retry_after:sendDocument')}\n- sendMessage network retry: {bot_runtime._get_meta_counter(deps, f'{bot_runtime._TELEGRAM_METRIC_PREFIX}network_retry:sendMessage')}\n- sendDocument network retry: {bot_runtime._get_meta_counter(deps, f'{bot_runtime._TELEGRAM_METRIC_PREFIX}network_retry:sendDocument')}\n\nCallback osservate (top):\n{callback_block}"


async def _admin_report_worker(application: Application) -> None:
    deps: bot_runtime.BotDependencies = application.bot_data["deps"]
    while True:
        try:
            await asyncio.sleep(300)
            await _maybe_send_periodic_admin_reports(application, deps)
            await _maybe_send_admin_anomaly_alerts(application, deps)
        except asyncio.CancelledError:
            raise
        except Exception:
            bot_runtime.logger.exception("Errore durante l'invio dei report admin periodici.")


async def _maybe_send_periodic_admin_reports(application: Application, deps: bot_runtime.BotDependencies) -> None:
    if not deps.settings.admin_user_ids:
        return
    now = datetime.now(ZoneInfo("Europe/Rome"))
    if _is_periodic_admin_report_enabled(deps, "daily"):
        await _maybe_send_admin_report_for_period(
            application,
            deps,
            period="daily",
            report_date=now.date().isoformat(),
            should_send=now.hour >= deps.settings.admin_daily_report_hour,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
        )
    if _is_periodic_admin_report_enabled(deps, "weekly"):
        await _maybe_send_admin_report_for_period(
            application,
            deps,
            period="weekly",
            report_date=now.date().isoformat(),
            should_send=now.weekday() == deps.settings.admin_weekly_report_day
            and now.hour >= deps.settings.admin_weekly_report_hour,
            since_days=7,
            title="Riepilogo admin settimanale DocMolder",
            require_new_users_or_completed_actions=True,
        )


async def _maybe_send_admin_report_for_period(
    application: Application,
    deps: bot_runtime.BotDependencies,
    *,
    period: str,
    report_date: str,
    should_send: bool,
    since_days: int,
    title: str,
    require_new_users_or_completed_actions: bool = False,
) -> None:
    if not should_send:
        return
    meta_key = f"admin_report_{period}_last_sent"
    if deps.session_store.get_meta(meta_key) == report_date:
        return
    if not _period_has_useful_admin_data(
        deps, since_days=since_days, require_new_users_or_completed_actions=require_new_users_or_completed_actions
    ):
        return
    report_text = _build_periodic_admin_report(deps, since_days=since_days, title=title)
    for admin_user_id in deps.settings.admin_user_ids:
        await bot_runtime._safe_send_message(application.bot, chat_id=admin_user_id, text=report_text, deps=deps)
    deps.session_store.set_meta(meta_key, report_date)


def _period_has_useful_admin_data(
    deps: bot_runtime.BotDependencies, *, since_days: int, require_new_users_or_completed_actions: bool = False
) -> bool:
    stats = deps.session_store.build_admin_stats()
    known_users_total = stats.known_users_last_24h if since_days <= 1 else stats.known_users_last_7d
    completed_actions_total = stats.completed_actions_last_24h if since_days <= 1 else stats.completed_actions_last_7d
    if require_new_users_or_completed_actions:
        return known_users_total > 0 or completed_actions_total > 0
    if completed_actions_total > 0:
        return True
    if deps.session_store.list_failed_actions(limit=1, since_days=since_days):
        return True
    return False


def _build_periodic_admin_report(deps: bot_runtime.BotDependencies, *, since_days: int, title: str) -> str:
    stats = deps.session_store.build_admin_stats()
    top_users = deps.session_store.list_top_users(limit=5, since_days=since_days)
    failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=since_days)
    recent_failed_jobs = deps.session_store.list_recent_jobs(
        limit=5, statuses=(JobStatus.FAILED,), since_days=since_days
    )
    recent_completed_jobs = deps.session_store.list_recent_jobs(
        limit=5, statuses=(JobStatus.SUCCEEDED,), since_days=since_days
    )
    if since_days <= 1:
        activity_window_label = "ultime 24 ore"
        completed_jobs_heading = "Job completati nelle ultime 24 ore"
        failed_jobs_heading = "Job falliti nelle ultime 24 ore"
        slow_jobs_heading = "Job lenti nelle ultime 24 ore"
    else:
        activity_window_label = "della settimana"
        completed_jobs_heading = "Job completati della settimana"
        failed_jobs_heading = "Job falliti della settimana"
        slow_jobs_heading = "Job lenti della settimana"
    report_body = _build_admin_report(
        stats,
        top_users,
        failed_actions,
        recent_failed_jobs,
        recent_completed_jobs,
        _list_recent_slow_jobs(deps, since_days=since_days),
        activity_window_label=activity_window_label,
        completed_jobs_heading=completed_jobs_heading,
        failed_jobs_heading=failed_jobs_heading,
        slow_jobs_heading=slow_jobs_heading,
    )
    return f"{title}\n\n{report_body}"


async def _maybe_send_admin_anomaly_alerts(application: Application, deps: bot_runtime.BotDependencies) -> None:
    if not deps.settings.admin_user_ids:
        return
    now = datetime.now(timezone.utc)
    for alert in _detect_admin_anomaly_alerts(deps):
        if not _should_send_admin_alert(deps, alert["key"], alert["signature"], now):
            bot_runtime._increment_meta_counter(deps, _admin_alert_meta_key(alert["key"], "suppressed_count"))
            continue
        alert_text = _append_admin_alert_digest(deps, alert["key"], alert["text"])
        for admin_user_id in deps.settings.admin_user_ids:
            try:
                await bot_runtime._safe_send_message(application.bot, chat_id=admin_user_id, text=alert_text, deps=deps)
            except TelegramError:
                bot_runtime.logger.exception("Impossibile inviare l'allerta admin %s a %s", alert["key"], admin_user_id)
        deps.session_store.set_meta(_admin_alert_meta_key(alert["key"], "last_signature"), alert["signature"])
        deps.session_store.set_meta(_admin_alert_meta_key(alert["key"], "last_sent_at"), now.isoformat())
        deps.session_store.set_meta(_admin_alert_meta_key(alert["key"], "suppressed_count"), "0")


def _detect_admin_anomaly_alerts(deps: bot_runtime.BotDependencies) -> list[AdminAlertPayload]:
    settings = deps.settings
    window_minutes = max(5, settings.admin_alert_window_minutes)
    finished_jobs = deps.session_store.list_recent_jobs(
        limit=100, statuses=(JobStatus.SUCCEEDED, JobStatus.FAILED), since_minutes=window_minutes
    )
    failed_jobs = [job for job in finished_jobs if job.status == JobStatus.FAILED]
    alerts: list[AdminAlertPayload] = []
    if finished_jobs and failed_jobs:
        failure_rate_percent = round(len(failed_jobs) / len(finished_jobs) * 100)
        if (
            len(finished_jobs) >= settings.admin_alert_min_finished_jobs
            and failure_rate_percent >= settings.admin_alert_failure_rate_percent
        ):
            latest_failed_job_id = max((job.id for job in failed_jobs))
            alerts.append(
                {
                    "key": "failure-rate",
                    "signature": f"{latest_failed_job_id}:{len(failed_jobs)}/{len(finished_jobs)}",
                    "text": _build_failure_rate_alert_text(
                        finished_jobs=finished_jobs,
                        failed_jobs=failed_jobs,
                        window_minutes=window_minutes,
                        threshold_percent=settings.admin_alert_failure_rate_percent,
                    ),
                }
            )
    repeated_threshold = max(2, settings.admin_alert_repeated_failures_threshold)
    if failed_jobs:
        failed_action_counts = deps.session_store.list_failed_actions(limit=5, since_minutes=window_minutes)
        for action_stat in failed_action_counts:
            if action_stat.total < repeated_threshold:
                continue
            action_failed_jobs = [job for job in failed_jobs if job.action == action_stat.action][:5]
            latest_failed_job_id = max((job.id for job in action_failed_jobs))
            alerts.append(
                {
                    "key": f"repeated-failures:{action_stat.action}",
                    "signature": f"{latest_failed_job_id}:{action_stat.total}",
                    "text": _build_repeated_failures_alert_text(
                        action_stat=action_stat,
                        failed_jobs=action_failed_jobs,
                        window_minutes=window_minutes,
                        threshold_count=repeated_threshold,
                    ),
                }
            )
    return alerts


def _should_send_admin_alert(deps: bot_runtime.BotDependencies, key: str, signature: str, now: datetime) -> bool:
    last_signature = deps.session_store.get_meta(_admin_alert_meta_key(key, "last_signature"))
    if last_signature == signature:
        return False
    cooldown_minutes = max(1, deps.settings.admin_alert_cooldown_minutes)
    last_sent_raw = deps.session_store.get_meta(_admin_alert_meta_key(key, "last_sent_at"))
    last_sent_at = bot_runtime._parse_meta_datetime(last_sent_raw)
    if last_sent_at is None:
        return True
    return now - last_sent_at >= timedelta(minutes=cooldown_minutes)


def _build_failure_rate_alert_text(
    *, finished_jobs: list[JobRecord], failed_jobs: list[JobRecord], window_minutes: int, threshold_percent: int
) -> str:
    failure_rate_percent = round(len(failed_jobs) / len(finished_jobs) * 100)
    action_counts: dict[str, int] = {}
    for job in failed_jobs:
        action_counts[job.action] = action_counts.get(job.action, 0) + 1
    top_actions = "\n".join(
        (
            f"- {bot_results._action_label(action)}: {total}"
            for action, total in sorted(action_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        )
    )
    recent_block = "\n".join((bot_results._format_job_line(job) for job in failed_jobs[:3]))
    return f"Allerta admin DocMolder\nSegnale: tasso di fallimento anomalo negli ultimi {window_minutes} minuti.\n- Job conclusi: {len(finished_jobs)}\n- Job falliti: {len(failed_jobs)} ({failure_rate_percent}%)\n- Soglia configurata: {threshold_percent}%\n\nAzioni coinvolte:\n{top_actions}\n\nUltimi job falliti:\n{recent_block}\n\nProssimo controllo: apri /admin > Coda oppure esegui docmolder-healthcheck; se continua, segui docs/VPS_RUNBOOK.md."


def _build_repeated_failures_alert_text(
    *, action_stat: AdminActionStat, failed_jobs: list[JobRecord], window_minutes: int, threshold_count: int
) -> str:
    recent_block = "\n".join((bot_results._format_job_line(job) for job in failed_jobs))
    return f"Allerta admin DocMolder\nSegnale: errori ripetuti su {bot_results._action_label(action_stat.action)} negli ultimi {window_minutes} minuti.\n- Job falliti per questa azione: {action_stat.total}\n- Soglia configurata: {threshold_count}\n\nUltimi job falliti per questa azione:\n{recent_block}\n\nProssimo controllo: apri /admin > Coda e verifica gli ultimi job; per mitigare usa manutenzione temporanea dal runbook."


def _admin_alert_meta_key(key: str, suffix: str) -> str:
    return f"admin_alert:{key}:{suffix}"


def _append_admin_alert_digest(deps: bot_runtime.BotDependencies, key: str, text: str) -> str:
    suppressed_count = bot_runtime._get_meta_counter(deps, _admin_alert_meta_key(key, "suppressed_count"))
    if suppressed_count <= 0:
        return text
    return f"{text}\n\nNel frattempo ho soppresso {suppressed_count} alert simili per evitare spam."
