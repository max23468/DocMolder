from __future__ import annotations
import logging
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from docmolder.access_control import (
    ACCESS_STATUS_APPROVED as _ACCESS_STATUS_APPROVED,
    ACCESS_STATUS_REJECTED as _ACCESS_STATUS_REJECTED,
    is_admin as _is_admin,
    set_dynamic_access_status as _set_dynamic_access_status,
)
from docmolder.logging_utils import log_event
from docmolder.messages import ADMIN_ONLY_MESSAGE
from docmolder.models import JobStatus
import docmolder.admin_reporting as admin_reporting
import docmolder.bot_results as bot_results
import docmolder.bot_runtime as bot_runtime


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    bot_runtime._record_command_metric(deps, "admin")
    stats = deps.session_store.build_admin_stats()
    top_users = deps.session_store.list_top_users(limit=5, since_days=7)
    failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=7)
    recent_failed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
    recent_completed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))
    slow_jobs = admin_reporting._list_recent_slow_jobs(deps)
    await message.reply_text(
        admin_reporting._build_admin_report(
            stats, top_users, failed_actions, recent_failed_jobs, recent_completed_jobs, slow_jobs
        ),
        reply_markup=bot_runtime._build_admin_keyboard(deps),
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(ADMIN_ONLY_MESSAGE)
        return
    if user is None:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    if bot_runtime._is_replayed_callback(
        deps, user_id=user.id, callback_data=query.data or "", message_id=getattr(query.message, "message_id", None)
    ):
        await query.edit_message_text("Azione già ricevuta poco fa. Usa Aggiorna se vuoi vedere lo stato più recente.")
        return
    action = (query.data or "").removeprefix("admin:")
    bot_runtime._record_callback_metric(deps, f"admin:{action or 'overview'}")
    if action == "pause":
        bot_runtime._set_service_mode(deps, bot_runtime._SERVICE_MODE_MAINTENANCE)
        bot_runtime._append_audit_log(
            deps, "service_mode", actor_user_id=user.id, outcome="maintenance", detail="callback:admin:pause"
        )
        log_event(
            bot_runtime.logger,
            logging.INFO,
            "admin_service_mode_changed",
            actor_user_id=user.id,
            service_mode="maintenance",
        )
        body = f"Console admin DocMolder\nServizio impostato in modalità manutenzione.\n\n{admin_reporting._build_admin_queue_report(deps)}"
    elif action == "resume":
        bot_runtime._set_service_mode(deps, bot_runtime._SERVICE_MODE_NORMAL)
        bot_runtime._append_audit_log(
            deps, "service_mode", actor_user_id=user.id, outcome="normal", detail="callback:admin:resume"
        )
        log_event(
            bot_runtime.logger, logging.INFO, "admin_service_mode_changed", actor_user_id=user.id, service_mode="normal"
        )
        body = f"Console admin DocMolder\nServizio riattivato.\n\n{admin_reporting._build_admin_queue_report(deps)}"
    elif action == "queue":
        body = admin_reporting._build_admin_queue_report(deps)
    elif action == "health":
        body = admin_reporting._build_admin_health_report(deps)
    elif action == "metrics":
        body = admin_reporting._build_telegram_metrics_report(deps)
    elif action == "maintenance":
        body = admin_reporting._build_admin_maintenance_overview(deps)
    elif action == "failed":
        failed_job = bot_results._resolve_job_selector(deps, "failed")
        body = (
            bot_results._build_user_history_job_detail(failed_job)
            if failed_job is not None
            else "Non vedo job falliti recenti."
        )
    elif action == "running":
        running_job = bot_results._resolve_job_selector(deps, "running")
        body = (
            bot_results._build_user_history_job_detail(running_job)
            if running_job is not None
            else "Non vedo job in esecuzione."
        )
    elif action == "queued":
        queued_job = bot_results._resolve_job_selector(deps, "queued")
        body = (
            bot_results._build_user_history_job_detail(queued_job)
            if queued_job is not None
            else "Non vedo job in coda."
        )
    elif action == "succeeded":
        succeeded_job = bot_results._resolve_job_selector(deps, "succeeded")
        body = (
            bot_results._build_user_history_job_detail(succeeded_job)
            if succeeded_job is not None
            else "Non vedo job riusciti recenti."
        )
    elif action == "latest":
        latest_job = bot_results._resolve_job_selector(deps, "latest")
        body = (
            bot_results._build_user_history_job_detail(latest_job)
            if latest_job is not None
            else "Non vedo job recenti."
        )
    else:
        stats = deps.session_store.build_admin_stats()
        top_users = deps.session_store.list_top_users(limit=5, since_days=7)
        failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=7)
        recent_failed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
        recent_completed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))
        slow_jobs = admin_reporting._list_recent_slow_jobs(deps)
        body = admin_reporting._build_admin_report(
            stats, top_users, failed_actions, recent_failed_jobs, recent_completed_jobs, slow_jobs
        )
    try:
        await query.edit_message_text(body, reply_markup=bot_runtime._build_admin_keyboard(deps))
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


async def handle_access_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if user is None or not _is_admin(user.id, deps.settings):
        await query.edit_message_text(ADMIN_ONLY_MESSAGE)
        return
    try:
        _, action, raw_user_id = (query.data or "").split(":", 2)
        target_user_id = int(raw_user_id)
    except (TypeError, ValueError):
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    if action == "approve":
        status = _ACCESS_STATUS_APPROVED
        outcome = "approved"
    elif action == "reject":
        status = _ACCESS_STATUS_REJECTED
        outcome = "rejected"
    else:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    _set_dynamic_access_status(deps, target_user_id, status)
    bot_runtime._append_audit_log(
        deps,
        "access_review",
        actor_user_id=user.id,
        target_user_id=target_user_id,
        outcome=outcome,
        detail=f"callback:access:{action}",
    )
    await query.edit_message_text(f"Richiesta accesso utente {target_user_id}: {outcome}.")
