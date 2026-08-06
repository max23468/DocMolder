from __future__ import annotations
import html
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from telegram import Update, User
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes
from docmolder.access_control import (
    ACCESS_STATUS_APPROVED as _ACCESS_STATUS_APPROVED,
    ACCESS_STATUS_BLOCKED as _ACCESS_STATUS_BLOCKED,
    ACCESS_STATUS_PENDING as _ACCESS_STATUS_PENDING,
    ACCESS_STATUS_REJECTED as _ACCESS_STATUS_REJECTED,
    get_dynamic_access_status as _get_dynamic_access_status,
    is_admin as _is_admin,
    is_authorized_for_deps as _is_authorized_for_deps,
    set_dynamic_access_status as _set_dynamic_access_status,
)
from docmolder.keyboards import build_access_review_keyboard, build_main_menu_keyboard
from docmolder.logging_utils import log_event
from docmolder.messages import ADMIN_ONLY_MESSAGE, PUBLIC_PRIVACY_URL
from docmolder.models import JobStatus
from docmolder.action_catalog import get_action_label, infer_session_analysis
import docmolder.admin_reporting as admin_reporting
import docmolder.bot_jobs as bot_jobs
import docmolder.bot_results as bot_results
import docmolder.bot_runtime as bot_runtime
import docmolder.bot_sessions as bot_sessions


async def access_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "access")
    await message.reply_text(_build_access_status_message(deps, user.id), reply_markup=build_main_menu_keyboard())


async def policy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    deps.session_store.register_user(user.id, user.username, user.first_name, user.last_name)
    bot_runtime._record_command_metric(deps, "policy")
    await message.reply_text(_build_policy_message(deps), reply_markup=build_main_menu_keyboard())


async def request_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    deps.session_store.register_user(user.id, user.username, user.first_name, user.last_name)
    bot_runtime._record_command_metric(deps, "request_access")
    current_status = _get_dynamic_access_status(deps, user.id)
    if _is_authorized_for_deps(user.id, deps):
        await message.reply_text("Il tuo accesso a DocMolder è già attivo.", reply_markup=build_main_menu_keyboard())
        return
    if current_status == _ACCESS_STATUS_BLOCKED:
        await message.reply_text(
            "Il tuo accesso è sospeso. Contatta l'admin del bot per una riattivazione.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    if current_status == _ACCESS_STATUS_PENDING:
        await message.reply_text(
            "Accesso non ancora attivo. La richiesta è già in attesa di approvazione admin.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    _set_dynamic_access_status(deps, user.id, _ACCESS_STATUS_PENDING)
    bot_runtime._append_audit_log(
        deps, "request_access", actor_user_id=user.id, outcome="pending", target_user_id=user.id
    )
    await _notify_admins_about_access_request(user, context, deps)
    await message.reply_text(
        "Richiesta accesso inviata all'admin. Ti basta attendere: quando viene approvata potrai usare il bot.",
        reply_markup=build_main_menu_keyboard(),
    )


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


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    bot_runtime._record_command_metric(deps, "queue")
    await message.reply_text(
        admin_reporting._build_admin_queue_report(deps), reply_markup=bot_runtime._build_admin_keyboard(deps)
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    bot_runtime._record_command_metric(deps, "health")
    await message.reply_text(
        admin_reporting._build_admin_health_report(deps), reply_markup=bot_runtime._build_admin_keyboard(deps)
    )


async def maintenance_overview_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    bot_runtime._record_command_metric(deps, "maintenance_overview")
    await message.reply_text(
        admin_reporting._build_admin_maintenance_overview(deps), reply_markup=bot_runtime._build_admin_keyboard(deps)
    )


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "pause")
    bot_runtime._set_service_mode(deps, bot_runtime._SERVICE_MODE_MAINTENANCE)
    bot_runtime._append_audit_log(
        deps, "service_mode", actor_user_id=user.id, outcome="maintenance", detail="command:/pause"
    )
    log_event(
        bot_runtime.logger,
        logging.INFO,
        "admin_service_mode_changed",
        actor_user_id=user.id,
        service_mode="maintenance",
    )
    await message.reply_text(
        "Servizio messo in modalità manutenzione. I nuovi comandi utente vengono bloccati finché non riattivi il servizio.",
        reply_markup=bot_runtime._build_admin_keyboard(deps),
    )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "resume")
    bot_runtime._set_service_mode(deps, bot_runtime._SERVICE_MODE_NORMAL)
    bot_runtime._append_audit_log(
        deps, "service_mode", actor_user_id=user.id, outcome="normal", detail="command:/resume"
    )
    log_event(
        bot_runtime.logger, logging.INFO, "admin_service_mode_changed", actor_user_id=user.id, service_mode="normal"
    )
    await message.reply_text(
        "Servizio riattivato. Il bot accetta di nuovo richieste utente normali.",
        reply_markup=bot_runtime._build_admin_keyboard(deps),
    )


async def metrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    bot_runtime._record_command_metric(deps, "metrics")
    await message.reply_text(
        admin_reporting._build_telegram_metrics_report(deps), reply_markup=bot_runtime._build_admin_keyboard(deps)
    )


async def job_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    bot_runtime._record_command_metric(deps, "job")
    raw_selector = context.args[0].strip().lower() if getattr(context, "args", None) else ""
    job = bot_results._resolve_job_selector(deps, raw_selector)
    if job is None:
        await message.reply_text(
            "Usa `/job <id>`, `/job latest`, `/job failed`, `/job running`, `/job queued` oppure `/job succeeded`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    await message.reply_text(bot_results._build_user_history_job_detail(job))


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "retry")
    raw_args = [str(arg).strip().lower() for arg in getattr(context, "args", []) if str(arg).strip()]
    if not raw_args:
        await message.reply_text(
            "Usa `/retry <id>` oppure `/retry latest|failed|running|queued|succeeded` per rilanciare un job esistente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    selector = raw_args[0]
    disable_auto_rotate = "--no-auto-rotate" in raw_args[1:] or "no-auto-rotate" in raw_args[1:]
    source_job = bot_results._resolve_job_selector(deps, selector)
    if source_job is None:
        await message.reply_text(
            "Non trovo il job richiesto da rilanciare. Puoi usare un id oppure `latest`, `failed`, `running`, `queued`, `succeeded`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if not bot_jobs._has_capacity_for_new_job(source_job.user_id, deps):
        await message.reply_text(
            f"L'utente {source_job.user_id} ha già raggiunto il limite di job attivi. Riprova più tardi."
        )
        return
    rerun_job = await bot_jobs._enqueue_job_from_existing_payload(
        context=context,
        source_job=source_job,
        reply_to_message_id=message.message_id,
        auto_rotate_pdf=False if disable_auto_rotate else None,
    )
    bot_runtime._append_audit_log(
        deps,
        "admin_retry_job",
        actor_user_id=user.id,
        target_user_id=source_job.user_id,
        outcome="queued",
        detail=f"source_job_id={source_job.id} rerun_job_id={rerun_job.id} no_auto_rotate={disable_auto_rotate}",
    )
    log_event(
        bot_runtime.logger,
        logging.INFO,
        "admin_job_retry_queued",
        actor_user_id=user.id,
        source_job_id=source_job.id,
        rerun_job_id=rerun_job.id,
        target_user_id=source_job.user_id,
        no_auto_rotate=disable_auto_rotate,
    )
    if disable_auto_rotate:
        await message.reply_text(bot_results._build_rerun_without_rotation_message(source_job, rerun_job.id))
        return
    await message.reply_text(bot_results._build_history_rerun_message(source_job, rerun_job.id))


async def access_review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    command = (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()
    bot_runtime._record_command_metric(deps, command.removeprefix("/"))
    target_user_id = _parse_target_user_id(context)
    if target_user_id is None:
        await message.reply_text(
            "Uso corretto: /approve_user <id>, /reject_user <id>, /suspend_user <id> oppure /reactivate_user <id>."
        )
        return
    if command == "/approve_user":
        status = _ACCESS_STATUS_APPROVED
        outcome = "approved"
    elif command == "/reactivate_user":
        status = _ACCESS_STATUS_APPROVED
        outcome = "reactivated"
    elif command == "/suspend_user":
        status = _ACCESS_STATUS_BLOCKED
        outcome = "blocked"
    else:
        status = _ACCESS_STATUS_REJECTED
        outcome = "rejected"
    _set_dynamic_access_status(deps, target_user_id, status)
    bot_runtime._append_audit_log(
        deps,
        "access_review",
        actor_user_id=user.id,
        target_user_id=target_user_id,
        outcome=outcome,
        detail=f"command:{command}",
    )
    log_event(
        bot_runtime.logger,
        logging.INFO,
        "access_review_completed",
        actor_user_id=user.id,
        target_user_id=target_user_id,
        outcome=outcome,
    )
    await message.reply_text(f"Stato accesso utente {target_user_id}: {outcome}.")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_sessions._purge_expired_sessions(deps)
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


async def _maybe_notify_admins_about_new_user(user: User | None, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user is None:
        return
    deps = bot_runtime._get_dependencies(context)
    if not deps.settings.admin_user_ids:
        return
    is_new = deps.session_store.register_user(
        user_id=user.id, username=user.username, first_name=user.first_name, last_name=user.last_name
    )
    if not is_new:
        return
    notification_text = _build_new_user_notification(user)
    for admin_user_id in deps.settings.admin_user_ids:
        last_sent_at = bot_runtime._parse_meta_datetime(
            deps.session_store.get_meta(bot_runtime._new_user_admin_meta_key(admin_user_id, "last_sent_at"))
        )
        pending_count_key = bot_runtime._new_user_admin_meta_key(admin_user_id, "pending_count")
        now = datetime.now(timezone.utc)
        if (
            last_sent_at is not None
            and (now - last_sent_at).total_seconds() < bot_runtime._NEW_USER_NOTIFICATION_COOLDOWN_SECONDS
        ):
            bot_runtime._increment_meta_counter(deps, pending_count_key)
            continue
        pending_count = bot_runtime._get_meta_counter(deps, pending_count_key)
        admin_notification_text = notification_text
        if pending_count > 0:
            admin_notification_text = (
                f"{notification_text}\n\nNel frattempo altri {pending_count} utenti nuovi hanno già aperto il bot."
            )
        try:
            await bot_runtime._safe_send_message(
                context.bot,
                chat_id=admin_user_id,
                text=admin_notification_text,
                deps=deps,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            deps.session_store.set_meta(
                bot_runtime._new_user_admin_meta_key(admin_user_id, "last_sent_at"), now.isoformat()
            )
            deps.session_store.set_meta(pending_count_key, "0")
        except TelegramError:
            bot_runtime.logger.exception("Impossibile inviare la notifica nuovo utente all'admin %s", admin_user_id)


def _build_new_user_notification(user: User) -> str:
    timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M:%S")
    full_name_value = getattr(user, "full_name", None) or " ".join(
        (part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part)
    )
    full_name = html.escape(full_name_value or "Sconosciuto")
    username_value = getattr(user, "username", None)
    username = f"@{html.escape(username_value)}" if username_value else "non disponibile"
    profile_link = f'<a href="tg://user?id={user.id}">Apri profilo Telegram</a>'
    public_link = f' | <a href="https://t.me/{html.escape(username_value)}">Apri username</a>' if username_value else ""
    return f"Nuovo utente al primo accesso su <b>DocMolder</b>.\nData e ora: {timestamp}\nID utente: <code>{user.id}</code>\nNome: {full_name}\nUsername: {username}\nLink: {profile_link}{public_link}"


def _build_access_status_message(deps: bot_runtime.BotDependencies, user_id: int) -> str:
    session = deps.session_store.get(user_id)
    active_jobs = deps.session_store.count_active_jobs_for_user(user_id)
    recent_jobs = deps.session_store.list_user_jobs(user_id, limit=1)
    last_job = recent_jobs[0] if recent_jobs else None
    dynamic_status = _get_dynamic_access_status(deps, user_id) or "nessuno"
    lines = [
        "Stato accesso DocMolder",
        f"- Service mode: {bot_runtime._build_service_status_label(deps)}",
        f"- Accesso account: {('consentito' if _is_authorized_for_deps(user_id, deps) else 'non consentito')}",
        f"- Stato richiesta: {dynamic_status}",
        f"- Job attivi: {active_jobs}/{deps.settings.max_active_jobs_per_user}",
        f"- Sessione corrente: {('attiva' if session is not None and session.files else 'vuota')}",
    ]
    if session is not None and session.files:
        analysis = infer_session_analysis(session)
        lines.append(f"- File in sessione: {analysis.inventory.short_label}")
        if analysis.recommended_actions:
            lines.append(
                f"- Azioni consigliate: {', '.join((get_action_label(action) for action in analysis.recommended_actions[:3]))}"
            )
        if analysis.warnings:
            lines.append(f"- Avvisi sessione: {' '.join(analysis.warnings)}")
        if session.pending_action:
            lines.append(f"- Input atteso: {bot_results._action_label(session.pending_action)}")
    if last_job is not None:
        lines.append(
            f"- Ultimo job: #{last_job.id} {bot_results._action_label(last_job.action)} ({bot_results._format_job_status(last_job.status).lower()})"
        )
    else:
        lines.append("- Ultimo job: nessuno")
    lines.append("- Storico: usa /history per vedere dettagli recenti e rilanciare un job.")
    lines.append("- Dati e limiti: usa /start privacy o apri la pagina privacy.")
    lines.append(f"- Privacy: {PUBLIC_PRIVACY_URL}")
    return "\n".join(lines)


def _build_policy_message(deps: bot_runtime.BotDependencies) -> str:
    return f"Policy sintetica DocMolder\n\nUso supportato:\n- invia PDF, immagini o scansioni nella chat privata con il bot\n- ogni richiesta deve essere una trasformazione documentale chiara e circoscritta\n\nDati e retention:\n- i file caricati servono solo per creare il risultato richiesto\n- le directory job temporanee vengono pulite dopo circa {deps.settings.stale_job_retention_hours} ore\n- lo storico job live viene potato dopo {getattr(deps.settings, 'job_history_retention_days', 30)} giorni\n- il database conserva metadati tecnici dei job, preferenze minime, audit admin e metriche operative\n- il contenuto dei documenti non viene scritto nei log e non va inserito in issue, test o report\n\nCancellazione:\n- /reset azzera sessione, preferenze rapide e preset leggeri\n- dallo stesso percorso puoi cancellare tutti i dati live con conferma inline\n- i backup tecnici già creati non vengono riscritti e scadono con la loro retention breve\n\nPreset:\n- salvo solo impostazioni operative ripetute, come compressione, layout immagini PDF e output split\n- non salvo contenuti dei documenti o nomi file dentro i preset\n\nLimiti operativi:\n- file massimo: {deps.settings.max_file_size_mb} MB\n- file per sessione: {deps.settings.max_session_files}\n- job attivi per utente: {deps.settings.max_active_jobs_per_user}\n- upload rapido: {deps.settings.upload_burst_limit} file in {deps.settings.upload_burst_window_seconds} secondi\n\nDettagli pubblici: {PUBLIC_PRIVACY_URL}\n\nAccesso:\n- se il bot è ristretto, la richiesta accesso parte dal primo messaggio inviato al bot\n- in manutenzione i nuovi job utente sono sospesi, mentre gli admin possono usare /admin"


def _parse_target_user_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    raw_args = [str(arg).strip() for arg in getattr(context, "args", []) if str(arg).strip()]
    if not raw_args:
        return None
    try:
        return int(raw_args[0])
    except ValueError:
        return None


async def _notify_admins_about_access_request(
    user: User, context: ContextTypes.DEFAULT_TYPE, deps: bot_runtime.BotDependencies
) -> None:
    if not deps.settings.admin_user_ids:
        return
    full_name = html.escape(
        getattr(user, "full_name", None)
        or " ".join((part for part in [user.first_name, user.last_name] if part))
        or "Sconosciuto"
    )
    username = f"@{html.escape(user.username)}" if user.username else "non disponibile"
    text = f"Richiesta accesso DocMolder\nID utente: <code>{user.id}</code>\nNome: {full_name}\nUsername: {username}"
    for admin_user_id in deps.settings.admin_user_ids:
        try:
            await bot_runtime._safe_send_message(
                context.bot,
                chat_id=admin_user_id,
                text=text,
                deps=deps,
                parse_mode=ParseMode.HTML,
                reply_markup=build_access_review_keyboard(user.id),
                disable_web_page_preview=True,
            )
        except TelegramError:
            bot_runtime.logger.exception("Impossibile inviare richiesta accesso all'admin %s", admin_user_id)
