from __future__ import annotations
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes
from docmolder.access_control import is_admin as _is_admin, is_authorized_for_deps as _is_authorized_for_deps
from docmolder.keyboards import (
    build_compression_keyboard,
    build_history_keyboard,
    build_main_menu_keyboard,
    build_rotate_keyboard,
    build_result_pdf_keyboard,
    build_split_output_keyboard,
)
from docmolder.messages import UNAUTHORIZED_MESSAGE
from docmolder.models import (
    FileKind,
    JobPayload,
    JobRecord,
    JobStatus,
    PendingActionValue,
    SessionFile,
    SupportedAction,
    UserSession,
)
from docmolder.processing_models import ProcessingResult
from docmolder.action_catalog import (
    build_output_stem,
    build_session_file,
    get_action_label,
    infer_result_followup_actions,
    sanitize_filename,
)
import docmolder.bot_admin as bot_admin
import docmolder.bot_jobs as bot_jobs
import docmolder.bot_menu as bot_menu
import docmolder.bot_runtime as bot_runtime
import docmolder.bot_sessions as bot_sessions


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "history")
    jobs = deps.session_store.list_user_jobs(user.id, limit=5)
    if not jobs:
        await message.reply_text(
            "Non hai ancora uno storico lavori. Inviami immagini, PDF o un file Excel e terrò traccia degli ultimi job qui.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    await message.reply_text(
        _build_user_history_summary(jobs), reply_markup=build_history_keyboard([job.id for job in jobs])
    )


async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "last")
    await _rerun_latest_user_job(context=context, deps=deps, user_id=user.id, message=message)


async def _rerun_latest_user_job(
    *, context: ContextTypes.DEFAULT_TYPE, deps: bot_runtime.BotDependencies, user_id: int, message: Message
) -> None:
    jobs = deps.session_store.list_user_jobs(user_id, limit=1)
    if not jobs:
        await message.reply_text(
            "Non ho ancora un job da rilanciare per te. Inviami immagini, PDF o un file Excel e poi potrò ripetere l'ultimo flusso.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    if not bot_jobs._has_capacity_for_new_job(user_id, deps):
        await message.reply_text(bot_sessions._build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    source_job = jobs[0]
    rerun_job = await bot_jobs._enqueue_job_from_existing_payload(
        context=context, source_job=source_job, reply_to_message_id=message.message_id
    )
    await message.reply_text(_build_history_rerun_message(source_job, rerun_job.id))


async def handle_result_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_sessions._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.message.reply_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_admin._maybe_notify_admins_about_new_user(user, context)
    document = query.message.document
    if document is None or bot_sessions._infer_document_kind(document) != FileKind.PDF:
        await query.message.reply_text(
            "Non riesco più a recuperare questo PDF. Inviamelo di nuovo e lo converto subito.",
            reply_to_message_id=query.message.message_id,
        )
        return
    action = (query.data or "").removeprefix("result:")
    bot_runtime._record_callback_metric(deps, f"result:{action.split(':', 1)[0]}")
    if action.startswith("undo_rotate:"):
        if not bot_jobs._has_capacity_for_new_job(user.id, deps):
            await query.message.reply_text(
                bot_sessions._build_job_queue_limit_message(deps.settings.max_active_jobs_per_user),
                reply_to_message_id=query.message.message_id,
            )
            return
        try:
            source_job_id = int(action.removeprefix("undo_rotate:"))
        except ValueError:
            await query.message.reply_text(
                bot_runtime._invalid_callback_message(), reply_to_message_id=query.message.message_id
            )
            return
        source_job = deps.session_store.get_job(source_job_id)
        if source_job is None or source_job.user_id != user.id:
            await query.message.reply_text(
                "Non riesco più a recuperare l'operazione originale. Inviami di nuovo i file e la rifaccio senza rotazione automatica.",
                reply_to_message_id=query.message.message_id,
            )
            return
        rerun_job = await bot_jobs._enqueue_job_from_existing_payload(
            context=context, source_job=source_job, reply_to_message_id=query.message.message_id, auto_rotate_pdf=False
        )
        await query.message.reply_text(
            _build_rerun_without_rotation_message(source_job, rerun_job.id),
            reply_to_message_id=query.message.message_id,
        )
        return
    if not bot_jobs._has_capacity_for_new_job(user.id, deps):
        await query.message.reply_text(
            bot_sessions._build_job_queue_limit_message(deps.settings.max_active_jobs_per_user),
            reply_to_message_id=query.message.message_id,
        )
        return
    try:
        selected_action = SupportedAction(action)
    except ValueError:
        await query.message.reply_text(
            "Questa azione sul risultato non è supportata.", reply_to_message_id=query.message.message_id
        )
        return
    session = _build_result_pdf_session(user.id, document.file_id, document.file_name)
    deps.session_store.save(session)
    if selected_action == SupportedAction.PDF_COMPRESS:
        await query.message.reply_text(
            bot_menu._build_compression_prompt(user.id, deps),
            reply_to_message_id=query.message.message_id,
            reply_markup=build_compression_keyboard(
                bot_runtime._get_stored_compression_preset(deps, user.id, preset_only=True)
            ),
        )
        return
    if selected_action == SupportedAction.PDF_ROTATE:
        await query.message.reply_text(
            "Di quanti gradi vuoi ruotare tutte le pagine del PDF?\nScelta rapida: tocca uno dei pulsanti qui sotto.",
            reply_to_message_id=query.message.message_id,
            reply_markup=build_rotate_keyboard(),
        )
        return
    if selected_action == SupportedAction.PDF_SPLIT:
        session.pending_action = selected_action.value
        session.touch()
        deps.session_store.save(session)
        await query.message.reply_text(
            bot_menu._build_split_output_prompt(user.id, deps),
            reply_to_message_id=query.message.message_id,
            reply_markup=build_split_output_keyboard(
                bot_runtime._get_stored_split_output_choice(deps, user.id, preset_only=True)
            ),
        )
        return
    if selected_action in {
        SupportedAction.PDF_EXTRACT_PAGES,
        SupportedAction.PDF_REORDER_PAGES,
        SupportedAction.PDF_DELETE_PAGES,
        SupportedAction.PDF_WATERMARK,
    }:
        session.pending_action = selected_action.value
        session.touch()
        deps.session_store.save(session)
        await query.message.reply_text(
            bot_runtime._build_pending_action_prompt(selected_action), reply_to_message_id=query.message.message_id
        )
        return
    job = await bot_jobs._enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=selected_action,
        session=session,
    )
    deps.session_store.delete(user.id)
    await query.message.reply_text(
        bot_runtime._build_text_request_queued_message(selected_action, job.id, None),
        reply_to_message_id=query.message.message_id,
    )


async def handle_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_sessions._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.message.reply_text(UNAUTHORIZED_MESSAGE, reply_to_message_id=query.message.message_id)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.message.reply_text(
            bot_runtime._build_service_unavailable_message(), reply_to_message_id=query.message.message_id
        )
        return
    await bot_admin._maybe_notify_admins_about_new_user(user, context)
    try:
        _, action, raw_job_id = (query.data or "").split(":", 2)
        job_id = int(raw_job_id)
    except (TypeError, ValueError):
        await query.message.reply_text("Richiesta non valida.", reply_to_message_id=query.message.message_id)
        return
    bot_runtime._record_callback_metric(deps, f"history:{action}")
    job = deps.session_store.get_job(job_id)
    if job is None or job.user_id != user.id:
        await query.message.reply_text(
            "Non riesco più a recuperare questo job dal tuo storico.", reply_to_message_id=query.message.message_id
        )
        return
    if action == "details":
        await query.message.reply_text(
            _build_user_history_job_detail(job), reply_to_message_id=query.message.message_id
        )
        return
    if action == "rerun":
        if not bot_jobs._has_capacity_for_new_job(user.id, deps):
            await query.message.reply_text(
                bot_sessions._build_job_queue_limit_message(deps.settings.max_active_jobs_per_user),
                reply_to_message_id=query.message.message_id,
            )
            return
        rerun_job = await bot_jobs._enqueue_job_from_existing_payload(
            context=context, source_job=job, reply_to_message_id=query.message.message_id
        )
        await query.message.reply_text(
            _build_history_rerun_message(job, rerun_job.id), reply_to_message_id=query.message.message_id
        )
        return
    await query.message.reply_text("Azione storico non supportata.", reply_to_message_id=query.message.message_id)


def _resolve_job_selector(deps: bot_runtime.BotDependencies, selector: str) -> JobRecord | None:
    normalized = selector.strip().lower()
    if not normalized:
        return None
    if normalized == "latest":
        recent_jobs = deps.session_store.list_recent_jobs(limit=1)
        return recent_jobs[0] if recent_jobs else None
    if normalized == "failed":
        failed_jobs = deps.session_store.list_recent_jobs(limit=1, statuses=(JobStatus.FAILED,))
        return failed_jobs[0] if failed_jobs else None
    if normalized == "running":
        running_jobs = deps.session_store.list_recent_jobs(limit=1, statuses=(JobStatus.RUNNING,))
        return running_jobs[0] if running_jobs else None
    if normalized == "queued":
        queued_jobs = deps.session_store.list_recent_jobs(limit=1, statuses=(JobStatus.QUEUED,))
        return queued_jobs[0] if queued_jobs else None
    if normalized == "succeeded":
        succeeded_jobs = deps.session_store.list_recent_jobs(limit=1, statuses=(JobStatus.SUCCEEDED,))
        return succeeded_jobs[0] if succeeded_jobs else None
    try:
        job_id = int(normalized)
    except ValueError:
        return None
    return deps.session_store.get_job(job_id)


def _resolve_user_job_selector(deps: bot_runtime.BotDependencies, user_id: int, selector: str) -> JobRecord | None:
    normalized = selector.strip().lower()
    if not normalized:
        return None
    if normalized == "latest":
        recent_jobs = deps.session_store.list_user_jobs(user_id, limit=1)
        return recent_jobs[0] if recent_jobs else None
    status_selectors = {
        "failed": JobStatus.FAILED,
        "running": JobStatus.RUNNING,
        "queued": JobStatus.QUEUED,
        "succeeded": JobStatus.SUCCEEDED,
    }
    if normalized in status_selectors:
        status = status_selectors[normalized]
        jobs = deps.session_store.list_user_jobs(user_id, limit=1, statuses=(status,))
        return jobs[0] if jobs else None
    job = _resolve_job_selector(deps, normalized)
    if job is None or job.user_id != user_id:
        return None
    return job


def _format_job_line(job: JobRecord) -> str:
    action_label = _action_label(job.action)
    reference_time = job.finished_at or job.created_at
    timestamp = reference_time.astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m %H:%M")
    metric_parts: list[str] = []
    if job.duration_ms:
        metric_parts.append(_format_duration_ms(job.duration_ms))
    if job.processing_mode:
        metric_parts.append(job.processing_mode)
    metrics_suffix = f" | {', '.join(metric_parts)}" if metric_parts else ""
    suffix = f" - {job.error_message}" if job.error_message else ""
    return f"- Job #{job.id} | {action_label} | utente {job.user_id} | {timestamp}{metrics_suffix}{suffix}"


def _format_duration_ms(duration_ms: int) -> str:
    if duration_ms >= 1000:
        return f"{duration_ms / 1000:.1f}s"
    return f"{duration_ms}ms"


def _format_bytes(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def _format_percent(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{value / total * 100:.0f}%"


def _action_label(action: PendingActionValue) -> str:
    return get_action_label(action)


def _build_user_history_summary(jobs: list[JobRecord]) -> str:
    lines = [
        "Storico ultimi job",
        "",
        "Qui sotto trovi gli ultimi lavori raggruppati per stato e rilancio. Puoi aprire i dettagli o rilanciare un job.",
        "",
    ]
    grouped_jobs = [
        ("Rilanciati", [job for job in jobs if job.rerun_of_job_id is not None]),
        (
            "In lavorazione",
            [
                job
                for job in jobs
                if job.status in {JobStatus.QUEUED, JobStatus.RUNNING} and job.rerun_of_job_id is None
            ],
        ),
        ("Riusciti", [job for job in jobs if job.status == JobStatus.SUCCEEDED and job.rerun_of_job_id is None]),
        ("Falliti", [job for job in jobs if job.status == JobStatus.FAILED and job.rerun_of_job_id is None]),
    ]
    for heading, grouped in grouped_jobs:
        if not grouped:
            continue
        lines.append(f"{heading}:")
        lines.extend((_format_user_history_line(job) for job in grouped))
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _format_user_history_line(job: JobRecord) -> str:
    reference_time = job.finished_at or job.created_at
    timestamp = reference_time.astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m %H:%M")
    status_label = {
        JobStatus.QUEUED: "in coda",
        JobStatus.RUNNING: "in lavorazione",
        JobStatus.SUCCEEDED: "completato",
        JobStatus.FAILED: "fallito",
    }[job.status]
    rerun_suffix = f" | rilancio di #{job.rerun_of_job_id}" if job.rerun_of_job_id is not None else ""
    return f"- Job #{job.id} | {_action_label(job.action)} | {status_label} | {timestamp}{rerun_suffix}"


def _build_user_history_job_detail(job: JobRecord) -> str:
    payload = JobPayload.from_json(job.payload_json)
    session_files = _payload_session_files(payload)
    reference_time = (job.finished_at or job.created_at).astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")
    detail_lines = [
        f"Dettaglio Job #{job.id}",
        f"Azione: {_action_label(job.action)}",
        f"Stato: {_format_job_status(job.status)}",
        f"Riferimento temporale: {reference_time}",
        f"File sorgente: {_build_payload_file_summary(payload)}",
        f"Nome output base: {build_output_stem(SupportedAction(job.action), session_files)}",
    ]
    if job.rerun_of_job_id is not None:
        detail_lines.append(f"Origine rilancio: job #{job.rerun_of_job_id}")
    if payload.compression_preset:
        detail_lines.append(f"Compressione: {payload.compression_preset.value}")
    if payload.page_selection:
        detail_lines.append(f"Selezione pagine: {payload.page_selection}")
    if job.action.startswith("images_to_pdf"):
        detail_lines.append("Impaginazione: A4" if payload.image_pdf_use_a4 else "Impaginazione: formato originale")
    if job.action == SupportedAction.DOCUMENT_PHOTO_FIX.value:
        detail_lines.append(f"Profilo scansione: {bot_menu._document_photo_mode_label(payload.document_photo_mode)}")
    if job.action == SupportedAction.PDF_SPLIT.value:
        detail_lines.append(
            "Output divisione: ZIP unico" if payload.split_output_zip else "Output divisione: PDF separati"
        )
    detail_lines.append(
        "Rotazione automatica PDF: attiva" if payload.auto_rotate_pdf else "Rotazione automatica PDF: disattiva"
    )
    if payload.rotate_degrees is not None:
        detail_lines.append(f"Rotazione manuale: {payload.rotate_degrees} gradi")
    if payload.watermark_text:
        detail_lines.append(f'Watermark: "{payload.watermark_text}"')
    if job.processing_mode:
        detail_lines.append(f"Strategia finale: {job.processing_mode}")
    if job.duration_ms is not None:
        detail_lines.append(f"Durata: {_format_duration_ms(job.duration_ms)}")
    if job.input_bytes is not None and job.output_bytes is not None:
        detail_lines.append(f"Dimensioni: {_format_bytes(job.input_bytes)} -> {_format_bytes(job.output_bytes)}")
    if job.result_message:
        detail_lines.append(f"Esito: {job.result_message}")
    if job.error_message:
        detail_lines.append(f"Errore: {job.error_message}")
    detail_lines.append("Puoi usare il pulsante del job per rilanciarlo e recuperare di nuovo il risultato.")
    return "\n".join(detail_lines)


def _payload_session_files(payload: JobPayload) -> list[SessionFile]:
    return [
        SessionFile(telegram_file_id=item.telegram_file_id, file_name=item.file_name, kind=item.kind)
        for item in payload.files
    ]


def _build_payload_file_summary(payload: JobPayload) -> str:
    file_count = len(payload.files)
    if file_count == 0:
        return "0"
    preview = ", ".join((sanitize_filename(item.file_name) for item in payload.files[:3]))
    remaining = file_count - min(file_count, 3)
    if remaining:
        preview += f" e altri {remaining}"
    return f"{file_count} ({preview})"


def _build_history_rerun_message(source_job: JobRecord, job_id: int) -> str:
    payload = JobPayload.from_json(source_job.payload_json)
    if source_job.action == SupportedAction.PDF_SPLIT.value:
        raw_value = "zip" if payload.split_output_zip else "pdf separati"
        base_message = bot_runtime._build_pending_action_queued_message(SupportedAction.PDF_SPLIT, job_id, raw_value)
        return f"Ripeto il job #{source_job.id} dal tuo storico.\n{base_message}"
    base_message = bot_runtime._build_text_request_queued_message(
        SupportedAction(source_job.action), job_id, payload.compression_preset
    )
    if source_job.action in {
        SupportedAction.IMAGES_TO_PDF_CROP.value,
        SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE.value,
    }:
        return f"Ripeto il job #{source_job.id} dal tuo storico.\n{base_message}\n\nNota: questo rilancia il ritaglio sulle immagini sorgenti. Per tagliare i bordi del PDF risultato, usa il pulsante `Taglia bordi PDF` sotto il file oppure reinvia il PDF e scrivi `taglia i bordi di questo pdf`."
    return f"Ripeto il job #{source_job.id} dal tuo storico.\n{base_message}"


def _format_job_status(status: JobStatus) -> str:
    return {
        JobStatus.QUEUED: "In coda",
        JobStatus.RUNNING: "In lavorazione",
        JobStatus.SUCCEEDED: "Completato",
        JobStatus.FAILED: "Fallito",
    }[status]


def _build_result_pdf_session(user_id: int, file_id: str, file_name: str | None) -> UserSession:
    return UserSession(user_id=user_id, files=[build_session_file(file_id, file_name, FileKind.PDF)])


def _build_result_delivery_message(result: ProcessingResult, source_action: SupportedAction | None) -> str:
    if result.additional_outputs:
        return result.message
    if not result.output_name.lower().endswith(".pdf"):
        return result.message
    followup_actions = infer_result_followup_actions(source_action)
    if not followup_actions:
        return f"{result.message}\n\nPuoi usare /history per ripetere un job recente o /status per vedere stato e sessione."
    quick_labels = ", ".join((get_action_label(action) for action in followup_actions[:3]))
    return f"{result.message}\n\nSe vuoi, puoi continuare su questo PDF con: {quick_labels}.\nSelf-service rapido: /history per ripetere un job recente, /status per vedere stato e sessione."


def _build_result_followup_keyboard(
    result: ProcessingResult, source_action: SupportedAction | None, source_job_id: int | None
) -> InlineKeyboardMarkup | None:
    if result.additional_outputs:
        return None
    if not result.output_name.lower().endswith(".pdf"):
        return None
    return build_result_pdf_keyboard(
        quick_actions=infer_result_followup_actions(source_action),
        undo_rotation_job_id=source_job_id if result.auto_rotation_applied else None,
    )


def _build_rerun_without_rotation_message(source_job: JobRecord, job_id: int) -> str:
    payload = JobPayload.from_json(source_job.payload_json)
    action = SupportedAction(source_job.action)
    base_message = bot_runtime._build_text_request_queued_message(action, job_id, payload.compression_preset)
    return f"Ripeto la stessa operazione senza rotazione automatica del PDF.\n{base_message}"
