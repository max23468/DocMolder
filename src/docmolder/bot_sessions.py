from __future__ import annotations
import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
from telegram import Document, PhotoSize, Update
from telegram.ext import ContextTypes
from docmolder.access_control import (
    get_dynamic_access_status as _get_dynamic_access_status,
    is_authorized_for_deps as _is_authorized_for_deps,
)
from docmolder.keyboards import (
    build_delete_data_confirmation_keyboard,
    build_document_photo_mode_keyboard,
    build_images_pdf_margin_keyboard,
    build_images_pdf_layout_keyboard,
    build_main_menu_keyboard,
    build_split_output_keyboard,
)
from docmolder.excel_unlock import SUPPORTED_EXCEL_SUFFIXES
from docmolder.logging_utils import log_event
from docmolder.messages import (
    FILE_TOO_LARGE_MESSAGE,
    MIXED_SESSION_MESSAGE,
    PUBLIC_PRIVACY_URL,
    UNSUPPORTED_DOCUMENT_MESSAGE,
    UPLOAD_RATE_LIMIT_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    build_document_photo_mode_prompt,
    build_job_queue_limit_message,
    build_split_output_prompt,
    document_photo_mode_label,
)
from docmolder.models import CompressionPreset, FileKind, PendingActionValue, SupportedAction, UserSession
from docmolder.processing_models import A4_MARGIN_NONE_PX, A4_MARGIN_WIDE_PX, ProcessingUserError
from docmolder.action_catalog import build_session_file, get_action_label, infer_session_analysis
from docmolder.text_requests import (
    _extract_rotation_degrees,
    _extract_compression_preset,
    _infer_split_output_zip,
    _normalize_keyword_text,
    _normalize_page_selection_text,
    _parse_image_pdf_layout_choice,
    _parse_image_pdf_margin_choice,
    _parse_document_photo_mode_choice,
    _tokenize_keyword_text,
    _validate_page_input_text,
)
import docmolder.bot_results as bot_results
import docmolder.bot_runtime as bot_runtime
import docmolder.job_flow as job_flow


class PendingActionEnqueueKwargs(TypedDict, total=False):
    compression_preset: CompressionPreset
    page_selection: str
    watermark_text: str
    split_output_zip: bool
    split_page_groups: str
    split_chunk_size: int


def _get_or_create_session(user_id: int, deps: bot_runtime.BotDependencies) -> UserSession:
    session = deps.session_store.get(user_id)
    if session is None:
        session = UserSession(user_id=user_id)
        deps.session_store.save(session)
    return session


def _prepare_session_for_upload(
    user_id: int, deps: bot_runtime.BotDependencies
) -> tuple[UserSession, bool]:
    session = _get_or_create_session(user_id, deps)
    if session.pending_action is None or session.pending_action == SupportedAction.PDF_MERGE.value:
        return session, False
    deps.session_store.record_flow_event(
        user_id, session.created_at.isoformat(), "cancelled", session.pending_action
    )
    session = UserSession(user_id=user_id)
    deps.session_store.save(session)
    return session, True


def _cancel_pending_image_notification(user_id: int, deps: bot_runtime.BotDependencies) -> None:
    task = deps.pending_image_notifications.pop(user_id, None)
    if task is not None:
        task.cancel()


def _consume_upload_slot(user_id: int, deps: bot_runtime.BotDependencies) -> bool:
    now = datetime.now(timezone.utc)
    window_seconds = deps.settings.upload_burst_window_seconds
    max_uploads = deps.settings.upload_burst_limit
    history = deps.upload_history.get(user_id)
    if history is None:
        history = _load_persisted_upload_history(user_id, deps)
        deps.upload_history[user_id] = history
    threshold = now.timestamp() - window_seconds
    while history and history[0].timestamp() < threshold:
        history.popleft()
    if len(history) >= max_uploads:
        _persist_upload_history(user_id, deps, history)
        return False
    history.append(now)
    _persist_upload_history(user_id, deps, history)
    return True


def _upload_burst_meta_key(user_id: int) -> str:
    return f"{bot_runtime._UPLOAD_BURST_META_PREFIX}{user_id}"


def _load_persisted_upload_history(user_id: int, deps: bot_runtime.BotDependencies) -> deque[datetime]:
    raw_value = deps.session_store.get_meta(_upload_burst_meta_key(user_id))
    if not raw_value:
        return deque()
    try:
        raw_timestamps = json.loads(raw_value)
    except json.JSONDecodeError:
        return deque()
    if not isinstance(raw_timestamps, list):
        return deque()
    history: deque[datetime] = deque()
    threshold = datetime.now(timezone.utc).timestamp() - deps.settings.upload_burst_window_seconds
    for raw_timestamp in raw_timestamps:
        if not isinstance(raw_timestamp, int | float):
            continue
        if raw_timestamp < threshold:
            continue
        try:
            history.append(datetime.fromtimestamp(float(raw_timestamp), tz=timezone.utc))
        except (OSError, OverflowError, ValueError):
            continue
    return history


def _persist_upload_history(user_id: int, deps: bot_runtime.BotDependencies, history: deque[datetime]) -> None:
    timestamps = [round(item.timestamp(), 3) for item in history]
    meta_key = _upload_burst_meta_key(user_id)
    if not timestamps:
        deps.session_store.delete_meta(meta_key)
        return
    deps.session_store.set_meta(meta_key, json.dumps(timestamps, separators=(",", ":")))


def _validate_session_for_upload(session: UserSession, kind: FileKind, max_session_files: int) -> str | None:
    if len(session.files) >= max_session_files:
        return _build_session_file_limit_message(max_session_files)
    if session.files and any((item.kind != kind for item in session.files)):
        return MIXED_SESSION_MESSAGE
    return None


def _save_uploaded_file(session: UserSession, session_file, deps: bot_runtime.BotDependencies) -> None:
    session.files.append(session_file)
    session.pending_action = None
    session.touch()
    deps.session_store.save(session)
    deps.session_store.record_flow_event(
        session.user_id, session.created_at.isoformat(), "upload", session_file.kind.value
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "reset")
    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is not None:
        deps.session_store.record_flow_event(user.id, session.created_at.isoformat(), "reset")
    deps.session_store.delete(user.id)
    await message.reply_text(
        "Nuovo lavoro pronto. Ho svuotato soltanto i file e il passaggio in corso; preferenze, preset e storico sono rimasti invariati.",
        reply_markup=build_main_menu_keyboard(),
    )


async def handle_preferences_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if (query.data or "") != "preferences:clear":
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    deps.session_store.clear_user_preferences(user.id)
    deps.session_store.clear_user_presets(user.id)
    await query.edit_message_text(
        "Preferenze e preset ripristinati. File della sessione e storico lavori non sono stati toccati."
    )


async def handle_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    action = (query.data or "").removeprefix("session:")
    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if action == "new":
        if session is not None:
            deps.session_store.record_flow_event(user.id, session.created_at.isoformat(), "reset")
        deps.session_store.delete(user.id)
        await query.edit_message_text("Nuovo lavoro pronto. Inviami il primo file; preferenze e storico sono invariati.")
        return
    if session is None or not session.files:
        await query.edit_message_text("Non c'è un lavoro attivo. Inviami un file per iniziare.")
        return
    if action == "back" and (session.pending_action or "").startswith(
        f"{bot_runtime._PENDING_IMAGES_PDF_MARGIN_PREFIX}:"
    ):
        image_action = _extract_pending_images_pdf_action(
            session.pending_action or "", bot_runtime._PENDING_IMAGES_PDF_MARGIN_PREFIX
        )
        if image_action is not None:
            session.pending_action = _build_images_pdf_layout_pending_action(image_action)
            session.touch()
            deps.session_store.save(session)
            await query.edit_message_text(
                "Vuoi impaginare le immagini in A4 oppure mantenere il formato originale?",
                reply_markup=build_images_pdf_layout_keyboard(image_action.value),
            )
            return
    if action in {"cancel", "back"}:
        deps.session_store.record_flow_event(
            user.id, session.created_at.isoformat(), "cancelled", session.pending_action
        )
        session.pending_action = None
        session.touch()
        deps.session_store.save(session)
        session_text, session_keyboard = bot_runtime._build_session_reply(session, intro="Operazione annullata.")
        await query.edit_message_text(session_text, reply_markup=session_keyboard)
        return
    parts = action.split(":")
    try:
        index = int(parts[1])
    except (IndexError, ValueError):
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    if index < 0 or index >= len(session.files):
        await query.edit_message_text("Questo elenco non è più aggiornato. Usa il messaggio più recente.")
        return
    if parts[0] == "remove":
        session.files.pop(index)
    elif parts[0] == "move" and len(parts) == 3:
        target = index - 1 if parts[2] == "up" else index + 1 if parts[2] == "down" else -1
        if target < 0 or target >= len(session.files):
            await query.edit_message_text("Questo spostamento non è più disponibile.")
            return
        session.files[index], session.files[target] = session.files[target], session.files[index]
    else:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    if not session.files:
        deps.session_store.delete(user.id)
        await query.edit_message_text("Ho rimosso l'ultimo file. Inviami un nuovo documento per iniziare.")
        return
    session.pending_action = None
    session.touch()
    deps.session_store.save(session)
    session_text, session_keyboard = bot_runtime._build_session_reply(session, intro="Ordine aggiornato.")
    await query.edit_message_text(session_text, reply_markup=session_keyboard)


async def handle_delete_data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if user is None:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    action = (query.data or "").removeprefix("delete_data:")
    bot_runtime._record_callback_metric(deps, f"delete_data:{action or 'unknown'}")
    if action == "request":
        await query.edit_message_text(
            "Confermi la cancellazione completa dei tuoi dati live?\n\nVerranno rimossi sessione, preferenze, preset, storico job e metadati utente. I backup tecnici già creati non vengono riscritti retroattivamente.",
            reply_markup=build_delete_data_confirmation_keyboard(),
        )
        return
    if action == "cancel":
        await query.edit_message_text("Cancellazione completa annullata. Non ho modificato i tuoi dati.")
        return
    if action != "confirm":
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    _cancel_pending_image_notification(user.id, deps)
    report = deps.session_store.delete_user_data(user.id)
    bot_runtime._append_audit_log(
        deps,
        "user_data_deleted",
        actor_user_id=None,
        target_user_id=None,
        outcome="self_service",
        detail="source:/start-privacy",
    )
    log_event(
        bot_runtime.logger,
        logging.INFO,
        "user_data_deleted",
        outcome="self_service",
        jobs_deleted=report.jobs_deleted,
        usage_events_deleted=report.usage_events_deleted,
        flow_events_deleted=report.flow_events_deleted,
        meta_deleted=report.meta_deleted,
        audit_entries_scrubbed=report.audit_entries_scrubbed,
    )
    await query.edit_message_text(
        "Dati live cancellati. Ho rimosso sessione, preferenze, preset, storico job e metadati utente collegati al tuo account.\n\nNota: i backup tecnici già creati non vengono riscritti, ma restano coperti dalla retention breve."
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "status")
    await message.reply_text(_build_access_status_message(deps, user.id), reply_markup=build_main_menu_keyboard())


def _build_access_status_message(deps: bot_runtime.BotDependencies, user_id: int) -> str:
    session = deps.session_store.get(user_id)
    recent_jobs = deps.session_store.list_user_jobs(user_id, limit=1)
    last_job = recent_jobs[0] if recent_jobs else None
    lines = [
        "Stato accesso DocMolder",
        f"- Service mode: {bot_runtime._build_service_status_label(deps)}",
        f"- Accesso account: {('consentito' if _is_authorized_for_deps(user_id, deps) else 'non consentito')}",
        f"- Stato richiesta: {_get_dynamic_access_status(deps, user_id) or 'nessuno'}",
        f"- Job attivi: {deps.session_store.count_active_jobs_for_user(user_id)}/{deps.settings.max_active_jobs_per_user}",
        f"- Sessione corrente: {('attiva' if session is not None and session.files else 'vuota')}",
    ]
    if session is not None and session.files:
        analysis = infer_session_analysis(session)
        lines.append(f"- File in sessione: {analysis.inventory.short_label}")
        if analysis.recommended_actions:
            lines.append(
                f"- Azioni consigliate: {', '.join(get_action_label(action) for action in analysis.recommended_actions[:3])}"
            )
        if analysis.warnings:
            lines.append(f"- Avvisi sessione: {' '.join(analysis.warnings)}")
        if session.pending_action:
            lines.append(f"- Input atteso: {bot_results._action_label(session.pending_action)}")
    if last_job is None:
        lines.append("- Ultimo job: nessuno")
    else:
        lines.append(
            f"- Ultimo job: #{last_job.id} {bot_results._action_label(last_job.action)} "
            f"({bot_results._format_job_status(last_job.status).lower()})"
        )
    lines.extend(
        (
            "- Storico: usa /history per vedere dettagli recenti e rilanciare un job.",
            "- Dati e limiti: usa /start privacy o apri la pagina privacy.",
            f"- Privacy: {PUBLIC_PRIVACY_URL}",
        )
    )
    return "\n".join(lines)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_upload_metric(deps, "document")
    document = message.document
    if document is None:
        return
    kind = bot_runtime._infer_document_kind(document)
    if kind is None:
        await message.reply_text(_build_unsupported_document_message(document))
        return
    if not _consume_upload_slot(user.id, deps):
        await message.reply_text(
            _build_upload_rate_limit_message(
                deps.settings.upload_burst_limit, deps.settings.upload_burst_window_seconds
            )
        )
        return
    if _exceeds_file_size_limit(document.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_build_file_too_large_message(deps.settings.max_file_size_mb))
        return
    session, restarted = _prepare_session_for_upload(user.id, deps)
    validation_error = _validate_session_for_upload(session, kind, deps.settings.max_session_files)
    if validation_error is not None:
        await message.reply_text(validation_error)
        return
    file_name = _build_document_session_file_name(document, kind)
    _save_uploaded_file(session, build_session_file(document.file_id, file_name, kind), deps)
    if kind == FileKind.IMAGE:
        _schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)
        return
    _cancel_pending_image_notification(user.id, deps)
    intro = "Ho annullato il passaggio precedente e iniziato un nuovo lavoro con questo file." if restarted else "File ricevuto."
    session_text, session_keyboard = bot_runtime._build_session_reply(session, intro=intro)
    await message.reply_text(session_text, reply_markup=session_keyboard)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_upload_metric(deps, "photo")
    photos = message.photo
    if not photos:
        return
    if not _consume_upload_slot(user.id, deps):
        await message.reply_text(
            _build_upload_rate_limit_message(
                deps.settings.upload_burst_limit, deps.settings.upload_burst_window_seconds
            )
        )
        return
    best_photo = _pick_best_photo(photos)
    if _exceeds_file_size_limit(best_photo.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_build_file_too_large_message(deps.settings.max_file_size_mb))
        return
    session, restarted = _prepare_session_for_upload(user.id, deps)
    validation_error = _validate_session_for_upload(session, FileKind.IMAGE, deps.settings.max_session_files)
    if validation_error is not None:
        await message.reply_text(validation_error)
        return
    generated_name = f"foto_{len(session.files) + 1}.jpg"
    _save_uploaded_file(session, build_session_file(best_photo.file_id, generated_name, FileKind.IMAGE), deps)
    if restarted:
        await message.reply_text("Ho annullato il passaggio precedente e iniziato un nuovo lavoro con questa foto.")
    _schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)


def _build_document_session_file_name(document: Document, kind: FileKind) -> str | None:
    if kind != FileKind.EXCEL:
        return document.file_name
    file_name = document.file_name
    suffix = Path(file_name or "").suffix.lower()
    if suffix in SUPPORTED_EXCEL_SUFFIXES:
        return file_name
    fallback_suffix = bot_runtime._EXCEL_SUFFIX_BY_MIME_TYPE.get(document.mime_type or "")
    if fallback_suffix is None:
        return file_name
    if not file_name:
        return f"excel_{document.file_id[:8]}{fallback_suffix}"
    return Path(file_name).with_suffix(fallback_suffix).name


def _build_unsupported_document_message(document: Document) -> str:
    mime_type = (document.mime_type or "").strip()
    file_name = (document.file_name or "").strip()
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if mime_type:
        hint = f"Tipo ricevuto: {mime_type}."
    elif suffix:
        hint = f"Estensione ricevuta: .{suffix}."
    else:
        hint = "Non riesco a riconoscere formato o estensione del file."
    return f"{UNSUPPORTED_DOCUMENT_MESSAGE}\n{hint}"


def _pick_best_photo(photos: list[PhotoSize]) -> PhotoSize:
    return max(photos, key=lambda item: item.file_size or 0)


def _exceeds_file_size_limit(file_size: int | None, max_file_size_mb: int) -> bool:
    if file_size is None:
        return False
    return file_size > max_file_size_mb * 1024 * 1024


def _build_file_too_large_message(max_file_size_mb: int) -> str:
    return f"{FILE_TOO_LARGE_MESSAGE} Limite attuale: {max_file_size_mb} MB. Prossimo passo: alleggerisci il file e reinvialo."


def _build_session_file_limit_message(max_session_files: int) -> str:
    return f"Hai raggiunto il numero massimo di file per questa sessione. Limite attuale: {max_session_files} file. Usa /reset per ricominciare oppure invia un gruppo più piccolo."


def _build_upload_rate_limit_message(upload_burst_limit: int, upload_burst_window_seconds: int) -> str:
    return f"{UPLOAD_RATE_LIMIT_MESSAGE} Limite attuale: {upload_burst_limit} file in {upload_burst_window_seconds} secondi. Prossimo passo: aspetta e riprendi dallo stesso file."


def _schedule_image_session_notification(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    _cancel_pending_image_notification(user_id, deps)
    task = asyncio.create_task(_send_image_session_notification(chat_id, user_id, context))
    deps.pending_image_notifications[user_id] = task


async def _send_image_session_notification(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    try:
        await asyncio.sleep(1.2)
        session = deps.session_store.get(user_id)
        if session is None or not session.files:
            return
        if {item.kind for item in session.files} != {FileKind.IMAGE}:
            return
        session_text, session_keyboard = bot_runtime._build_session_reply(
            session, intro=_build_image_session_intro(session)
        )
        await context.bot.send_message(chat_id=chat_id, text=session_text, reply_markup=session_keyboard)
    except asyncio.CancelledError:
        raise
    finally:
        current_task = deps.pending_image_notifications.get(user_id)
        if current_task is asyncio.current_task():
            deps.pending_image_notifications.pop(user_id, None)


def _build_image_session_intro(session: UserSession) -> str:
    image_count = sum((1 for item in session.files if item.kind == FileKind.IMAGE))
    if image_count == 1:
        return "Immagine ricevuta."
    return f"Ho ricevuto {image_count} immagini nella stessa sessione."


async def _handle_pending_session_input(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: UserSession,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    text: str,
) -> bool:
    deps = bot_runtime._get_dependencies(context)
    if session.pending_action is None:
        return False
    if session.pending_action.startswith(f"{bot_runtime._PENDING_IMAGES_PDF_LAYOUT_PREFIX}:"):
        return await _handle_pending_images_pdf_layout_input(
            update=update,
            context=context,
            session=session,
            user_id=user_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            text=text,
        )
    if session.pending_action.startswith(f"{bot_runtime._PENDING_IMAGES_PDF_MARGIN_PREFIX}:"):
        return await _handle_pending_images_pdf_margin_input(
            update=update,
            context=context,
            session=session,
            user_id=user_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            text=text,
        )
    if session.pending_action == bot_runtime._PENDING_DOCUMENT_PHOTO_MODE:
        return await _handle_pending_document_photo_mode_input(
            update=update,
            context=context,
            session=session,
            user_id=user_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            text=text,
        )
    raw_pending_action = session.pending_action
    pending_action = (
        SupportedAction.PDF_SPLIT
        if raw_pending_action in {bot_runtime._PENDING_PDF_SPLIT_GROUPS, bot_runtime._PENDING_PDF_SPLIT_CHUNKS}
        else SupportedAction(raw_pending_action)
    )
    if not job_flow.has_capacity_for_new_job(user_id, deps):
        await update.effective_message.reply_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return True
    try:
        enqueue_kwargs: PendingActionEnqueueKwargs = {}
        if pending_action == SupportedAction.PDF_COMPRESS:
            keyword_text = _normalize_keyword_text(text)
            compression_preset = _extract_compression_preset(keyword_text, _tokenize_keyword_text(keyword_text))
            if compression_preset is None:
                await update.effective_message.reply_text(
                    "Scegli un livello: leggera, media oppure forte. Puoi anche usare i pulsanti del messaggio precedente."
                )
                return True
            enqueue_kwargs["compression_preset"] = compression_preset
        elif pending_action in {
            SupportedAction.PDF_EXTRACT_PAGES,
            SupportedAction.PDF_REORDER_PAGES,
            SupportedAction.PDF_DELETE_PAGES,
        }:
            normalized_page_selection = _normalize_page_selection_text(text)
            _validate_page_input_text(normalized_page_selection)
            enqueue_kwargs["page_selection"] = normalized_page_selection
        elif pending_action == SupportedAction.PDF_ROTATE:
            rotate_degrees = _extract_rotation_degrees(_normalize_keyword_text(text))
            if rotate_degrees is None:
                await update.effective_message.reply_text(
                    "Non ho capito di quanto vuoi ruotare il PDF.\nScrivimi `90`, `180` oppure `270` gradi, oppure frasi come `giralo a destra`."
                )
                return True
            job = await job_flow.enqueue_job(
                deps=deps,
                user_id=user_id,
                chat_id=chat_id,
                reply_to_message_id=reply_to_message_id,
                action=pending_action,
                session=session,
                rotate_degrees=rotate_degrees,
            )
            deps.session_store.delete(user_id)
            await update.effective_message.reply_text(
                f"Rotazione manuale presa in carico di {rotate_degrees} gradi. Job #{job.id} in coda.\nTi invio il PDF appena è pronto."
            )
            return True
        elif pending_action == SupportedAction.PDF_WATERMARK:
            watermark_text = text.strip()
            if not watermark_text:
                await update.effective_message.reply_text(
                    "Il watermark testuale non può essere vuoto. Scrivimi una parola o una frase breve, ad esempio BOZZA."
                )
                return True
            enqueue_kwargs["watermark_text"] = watermark_text
        elif raw_pending_action == bot_runtime._PENDING_PDF_SPLIT_GROUPS:
            split_page_groups = text.strip()
            if not split_page_groups:
                await update.effective_message.reply_text(
                    "Scrivi almeno due gruppi separati da |, ad esempio 1-3 | 4-6."
                )
                return True
            enqueue_kwargs["split_page_groups"] = split_page_groups
            enqueue_kwargs["split_output_zip"] = True
        elif raw_pending_action == bot_runtime._PENDING_PDF_SPLIT_CHUNKS:
            if not text.strip().isdigit():
                await update.effective_message.reply_text(
                    "Scrivi quante pagine vuoi in ogni file, usando un numero intero. Esempio: 5."
                )
                return True
            enqueue_kwargs["split_chunk_size"] = int(text.strip())
            enqueue_kwargs["split_output_zip"] = True
        elif pending_action == SupportedAction.PDF_SPLIT:
            keyword_text = _normalize_keyword_text(text)
            split_output_zip = _infer_split_output_zip(keyword_text, _tokenize_keyword_text(keyword_text))
            if split_output_zip is None:
                await update.effective_message.reply_text(
                    build_split_output_prompt(
                        bot_runtime._get_stored_split_output_choice(deps, user_id, preset_only=True),
                        bot_runtime._get_stored_split_output_choice(deps, user_id),
                    ),
                    reply_markup=build_split_output_keyboard(
                        bot_runtime._get_stored_split_output_choice(deps, user_id, preset_only=True)
                    ),
                )
                return True
            enqueue_kwargs["split_output_zip"] = split_output_zip
        else:
            return False
        job = await job_flow.enqueue_job(
            deps=deps,
            user_id=user_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            action=pending_action,
            session=session,
            **enqueue_kwargs,
        )
    except ProcessingUserError as exc:
        await update.effective_message.reply_text(
            f"{exc}\n\n{bot_runtime._build_pending_action_prompt(pending_action)}"
        )
        return True
    deps.session_store.delete(user_id)
    if pending_action == SupportedAction.PDF_SPLIT:
        bot_runtime._record_split_output_choice(deps, user_id, enqueue_kwargs.get("split_output_zip") is True)
    elif pending_action == SupportedAction.PDF_COMPRESS:
        compression_preset = enqueue_kwargs.get("compression_preset")
        if compression_preset is not None:
            bot_runtime._record_user_choice(
                deps, user_id, bot_runtime._COMPRESSION_PRESET_KEY, compression_preset.value
            )
    raw_value = (
        "zip"
        if enqueue_kwargs.get("split_output_zip") is True
        else "pdf separati"
        if enqueue_kwargs.get("split_output_zip") is False
        else enqueue_kwargs.get("split_page_groups")
        or enqueue_kwargs.get("split_chunk_size")
        or enqueue_kwargs.get("page_selection")
        or enqueue_kwargs.get("watermark_text")
        or text
    )
    await update.effective_message.reply_text(
        bot_runtime._build_pending_action_queued_message(pending_action, job.id, str(raw_value))
    )
    return True


def _build_images_pdf_layout_pending_action(action: SupportedAction) -> PendingActionValue:
    return f"{bot_runtime._PENDING_IMAGES_PDF_LAYOUT_PREFIX}:{action.value}"


def _build_images_pdf_margin_pending_action(action: SupportedAction) -> PendingActionValue:
    return f"{bot_runtime._PENDING_IMAGES_PDF_MARGIN_PREFIX}:{action.value}"


def _extract_pending_images_pdf_action(pending_action: PendingActionValue, prefix: str) -> SupportedAction | None:
    if not pending_action.startswith(f"{prefix}:"):
        return None
    raw_action = pending_action.split(":", 1)[1]
    try:
        action = SupportedAction(raw_action)
    except ValueError:
        return None
    if not bot_runtime._is_image_pdf_action(action):
        return None
    return action


async def _handle_pending_images_pdf_layout_input(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: UserSession,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    text: str,
) -> bool:
    deps = bot_runtime._get_dependencies(context)
    action = _extract_pending_images_pdf_action(
        session.pending_action or "", bot_runtime._PENDING_IMAGES_PDF_LAYOUT_PREFIX
    )
    if action is None:
        return False
    use_a4 = _parse_image_pdf_layout_choice(text)
    if use_a4 is None:
        await update.effective_message.reply_text(
            "Dimmi se vuoi il PDF in A4 oppure nel formato originale.\nPuoi scrivere ad esempio `Si, impagina in A4` oppure `No, mantieni formato originale`."
        )
        return True
    if use_a4:
        session.pending_action = _build_images_pdf_margin_pending_action(action)
        session.touch()
        deps.session_store.save(session)
        await update.effective_message.reply_text(
            "Che bordi vuoi nell'impaginazione A4?\nPuoi scrivere ad esempio `bordi stretti`, `bordi larghi` oppure `senza bordi`.",
            reply_markup=build_images_pdf_margin_keyboard(action.value),
        )
        return True
    return await _enqueue_image_pdf_job_from_text(
        update=update,
        context=context,
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=action,
        session=session,
        image_pdf_use_a4=False,
        image_pdf_margin_px=A4_MARGIN_NONE_PX,
    )


async def _handle_pending_images_pdf_margin_input(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: UserSession,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    text: str,
) -> bool:
    action = _extract_pending_images_pdf_action(
        session.pending_action or "", bot_runtime._PENDING_IMAGES_PDF_MARGIN_PREFIX
    )
    if action is None:
        return False
    margin_px = _parse_image_pdf_margin_choice(text)
    if margin_px is None:
        await update.effective_message.reply_text(
            "Dimmi che bordi vuoi in A4.\nPuoi scrivere `bordi stretti`, `bordi larghi` oppure `senza bordi`."
        )
        return True
    return await _enqueue_image_pdf_job_from_text(
        update=update,
        context=context,
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=action,
        session=session,
        image_pdf_use_a4=True,
        image_pdf_margin_px=margin_px,
    )


async def _handle_pending_document_photo_mode_input(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: UserSession,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    text: str,
) -> bool:
    deps = bot_runtime._get_dependencies(context)
    mode = _parse_document_photo_mode_choice(text)
    if mode is None:
        await update.effective_message.reply_text(
            build_document_photo_mode_prompt(), reply_markup=build_document_photo_mode_keyboard()
        )
        return True
    if not job_flow.has_capacity_for_new_job(user_id, deps):
        await update.effective_message.reply_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return True
    job = await job_flow.enqueue_job(
        deps=deps,
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=SupportedAction.DOCUMENT_PHOTO_FIX,
        session=session,
        document_photo_mode=mode,
    )
    deps.session_store.delete(user_id)
    await update.effective_message.reply_text(
        f"{document_photo_mode_label(mode)} selezionato.\n{bot_runtime._build_text_request_queued_message(SupportedAction.DOCUMENT_PHOTO_FIX, job.id, None)}"
    )
    return True


async def _enqueue_image_pdf_job_from_text(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    action: SupportedAction,
    session: UserSession,
    image_pdf_use_a4: bool,
    image_pdf_margin_px: int,
) -> bool:
    deps = bot_runtime._get_dependencies(context)
    if not job_flow.has_capacity_for_new_job(user_id, deps):
        await update.effective_message.reply_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return True
    job = await job_flow.enqueue_job(
        deps=deps,
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=action,
        session=session,
        image_pdf_use_a4=image_pdf_use_a4,
        image_pdf_margin_px=image_pdf_margin_px,
    )
    bot_runtime._record_image_pdf_choice(
        deps, user_id, image_pdf_use_a4=image_pdf_use_a4, image_pdf_margin_px=image_pdf_margin_px
    )
    deps.session_store.delete(user_id)
    await update.effective_message.reply_text(
        f"{_describe_image_pdf_choice(image_pdf_use_a4, image_pdf_margin_px)}\n{bot_runtime._build_text_request_queued_message(action, job.id, None)}"
    )
    return True


async def _enqueue_image_pdf_job_from_callback(
    *,
    query,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    action: SupportedAction,
    session: UserSession,
    image_pdf_use_a4: bool,
    image_pdf_margin_px: int,
) -> None:
    deps = bot_runtime._get_dependencies(context)
    if not job_flow.has_capacity_for_new_job(user_id, deps):
        await query.edit_message_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    job = await job_flow.enqueue_job(
        deps=deps,
        user_id=user_id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=action,
        session=session,
        image_pdf_use_a4=image_pdf_use_a4,
        image_pdf_margin_px=image_pdf_margin_px,
    )
    bot_runtime._record_image_pdf_choice(
        deps, user_id, image_pdf_use_a4=image_pdf_use_a4, image_pdf_margin_px=image_pdf_margin_px
    )
    deps.session_store.delete(user_id)
    await query.edit_message_text(
        f"{_describe_image_pdf_choice(image_pdf_use_a4, image_pdf_margin_px)}\n{bot_runtime._build_text_request_queued_message(action, job.id, None)}"
    )


def _describe_image_pdf_choice(image_pdf_use_a4: bool, image_pdf_margin_px: int) -> str:
    if not image_pdf_use_a4:
        return "Perfetto, manterrò il formato originale delle immagini."
    if image_pdf_margin_px >= A4_MARGIN_WIDE_PX:
        border_label = "bordi larghi"
    elif image_pdf_margin_px <= A4_MARGIN_NONE_PX:
        border_label = "nessun bordo"
    else:
        border_label = "bordi stretti"
    return f"Perfetto, creerò il PDF in A4 con {border_label}."
