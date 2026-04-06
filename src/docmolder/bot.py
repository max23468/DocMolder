from __future__ import annotations

import asyncio
import html
import json
import logging
import unicodedata
from collections import deque
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Document, InlineKeyboardMarkup, PhotoSize, Update, User
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from docmolder.config import Settings
from docmolder.keyboards import (
    build_actions_keyboard,
    build_compression_keyboard,
    build_images_pdf_layout_keyboard,
    build_images_pdf_margin_keyboard,
    build_main_menu_keyboard,
    build_result_pdf_keyboard,
)
from docmolder.messages import (
    ADMIN_ONLY_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    GENERIC_ERROR_MESSAGE,
    HELP_MESSAGE,
    JOB_QUEUE_LIMIT_MESSAGE,
    MIXED_SESSION_MESSAGE,
    PROCESSING_MESSAGE,
    SESSION_EMPTY_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    UPLOAD_RATE_LIMIT_MESSAGE,
    WELCOME_MESSAGE,
)
from docmolder.models import AdminActionStat, AdminUserStat, CompressionPreset, FileKind, JobRecord, JobStatus, SupportedAction, UserSession
from docmolder.processing import (
    A4_MARGIN_NARROW_PX,
    A4_MARGIN_NONE_PX,
    A4_MARGIN_WIDE_PX,
    DocumentProcessor,
    ProcessingResult,
    ProcessingUserError,
)
from docmolder.services import (
    build_output_stem,
    build_session_file,
    describe_session,
    infer_supported_actions,
    sanitize_filename,
)
from docmolder.session_store import SQLiteSessionStore, SessionStore

logger = logging.getLogger(__name__)


class BotDependencies:
    def __init__(
        self,
        settings: Settings,
        session_store: SessionStore,
        processor: DocumentProcessor,
    ) -> None:
        self.settings = settings
        self.session_store = session_store
        self.processor = processor
        self.pending_image_notifications: dict[int, asyncio.Task[None]] = {}
        self.job_queue: asyncio.Queue[int] = asyncio.Queue()
        self.job_worker_task: asyncio.Task[None] | None = None
        self.cleanup_task: asyncio.Task[None] | None = None
        self.admin_report_task: asyncio.Task[None] | None = None
        self.upload_history: dict[int, deque[datetime]] = {}


def _is_authorized(user_id: int | None, settings: Settings) -> bool:
    if user_id is None:
        return False
    if not settings.allowed_user_ids:
        return True
    return user_id in settings.allowed_user_ids


def _is_admin(user_id: int | None, settings: Settings) -> bool:
    if user_id is None:
        return False
    return user_id in settings.admin_user_ids


def _get_dependencies(context: ContextTypes.DEFAULT_TYPE) -> BotDependencies:
    return context.application.bot_data["deps"]


async def _post_init(application: Application) -> None:
    deps: BotDependencies = application.bot_data["deps"]
    _run_cleanup_cycle(deps)
    requeued_jobs = deps.session_store.requeue_incomplete_jobs()
    for job in requeued_jobs:
        await deps.job_queue.put(job.id)
    if requeued_jobs:
        logger.info("Ripresi %s job incompleti dalla coda persistente.", len(requeued_jobs))
    deps.job_worker_task = asyncio.create_task(_job_worker(application))
    deps.cleanup_task = asyncio.create_task(_cleanup_worker(deps))
    deps.admin_report_task = asyncio.create_task(_admin_report_worker(application))


async def _post_shutdown(application: Application) -> None:
    deps: BotDependencies = application.bot_data["deps"]
    if deps.job_worker_task is not None:
        deps.job_worker_task.cancel()
        try:
            await deps.job_worker_task
        except asyncio.CancelledError:
            pass
    if deps.cleanup_task is not None:
        deps.cleanup_task.cancel()
        try:
            await deps.cleanup_task
        except asyncio.CancelledError:
            pass
    if deps.admin_report_task is not None:
        deps.admin_report_task.cancel()
        try:
            await deps.admin_report_task
        except asyncio.CancelledError:
            pass


def _get_or_create_session(user_id: int, deps: BotDependencies) -> UserSession:
    session = deps.session_store.get(user_id)
    if session is None:
        session = UserSession(user_id=user_id)
        deps.session_store.save(session)
    return session


def _purge_expired_sessions(deps: BotDependencies) -> None:
    deps.session_store.purge_expired(deps.settings.session_ttl_minutes)


def _cancel_pending_image_notification(user_id: int, deps: BotDependencies) -> None:
    task = deps.pending_image_notifications.pop(user_id, None)
    if task is not None:
        task.cancel()


def _consume_upload_slot(user_id: int, deps: BotDependencies) -> bool:
    now = datetime.now(timezone.utc)
    window_seconds = deps.settings.upload_burst_window_seconds
    max_uploads = deps.settings.upload_burst_limit
    history = deps.upload_history.setdefault(user_id, deque())
    threshold = now.timestamp() - window_seconds

    while history and history[0].timestamp() < threshold:
        history.popleft()

    if len(history) >= max_uploads:
        return False

    history.append(now)
    return True


def _has_capacity_for_new_job(user_id: int, deps: BotDependencies) -> bool:
    return deps.session_store.count_active_jobs_for_user(user_id) < deps.settings.max_active_jobs_per_user


def _filter_keyboard_for_session(session: UserSession) -> InlineKeyboardMarkup | None:
    allowed = set(infer_supported_actions(session))
    if not allowed:
        return None

    keyboard_rows = []
    for row in build_actions_keyboard().inline_keyboard:
        button = row[0]
        callback = (button.callback_data or "").removeprefix("action:")
        if callback in allowed:
            keyboard_rows.append(row)
    return InlineKeyboardMarkup(keyboard_rows)


def _is_image_pdf_action(action: SupportedAction) -> bool:
    return action in {
        SupportedAction.IMAGES_TO_PDF,
        SupportedAction.IMAGES_TO_PDF_CROP,
        SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
        SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
    }


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    await update.effective_message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=build_main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    await update.effective_message.reply_text(
        HELP_MESSAGE,
        reply_markup=build_main_menu_keyboard(),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_admin(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(ADMIN_ONLY_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    stats = deps.session_store.build_admin_stats()
    top_users = deps.session_store.list_top_users(limit=5, since_days=7)
    failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=7)
    recent_failed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
    recent_completed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))
    await update.effective_message.reply_text(
        _build_admin_report(stats, top_users, failed_actions, recent_failed_jobs, recent_completed_jobs)
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    _cancel_pending_image_notification(user.id, deps)
    deps.session_store.delete(user.id)
    await update.effective_message.reply_text(
        "Sessione azzerata. Puoi inviarmi nuovi file quando vuoi.",
        reply_markup=build_main_menu_keyboard(),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await update.effective_message.reply_text(
            SESSION_EMPTY_MESSAGE,
            reply_markup=build_main_menu_keyboard(),
        )
        return

    await update.effective_message.reply_text(
        f"{describe_session(session)}\nScegli cosa vuoi fare.",
        reply_markup=_filter_keyboard_for_session(session),
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    message = update.effective_message
    if not _is_authorized(user.id if user else None, deps.settings):
        await message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    document = message.document
    if document is None:
        return

    kind = _infer_document_kind(document)
    if kind is None:
        await message.reply_text("Per ora supporto solo PDF e immagini.")
        return

    if not _consume_upload_slot(user.id, deps):
        await message.reply_text(
            _build_upload_rate_limit_message(
                deps.settings.upload_burst_limit,
                deps.settings.upload_burst_window_seconds,
            )
        )
        return

    if _exceeds_file_size_limit(document.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_build_file_too_large_message(deps.settings.max_file_size_mb))
        return

    session = _get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text(_build_session_file_limit_message(deps.settings.max_session_files))
        return
    if session.files and any(item.kind != kind for item in session.files):
        await message.reply_text(MIXED_SESSION_MESSAGE)
        return

    session.files.append(build_session_file(document.file_id, document.file_name, kind))
    session.touch()
    deps.session_store.save(session)

    if kind == FileKind.IMAGE:
        _schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)
        return

    _cancel_pending_image_notification(user.id, deps)
    await message.reply_text(
        f"File ricevuto. {describe_session(session)}\nScegli la prossima azione.",
        reply_markup=_filter_keyboard_for_session(session),
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    message = update.effective_message
    if not _is_authorized(user.id if user else None, deps.settings):
        await message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    photos = message.photo
    if not photos:
        return

    if not _consume_upload_slot(user.id, deps):
        await message.reply_text(
            _build_upload_rate_limit_message(
                deps.settings.upload_burst_limit,
                deps.settings.upload_burst_window_seconds,
            )
        )
        return

    best_photo = _pick_best_photo(photos)
    if _exceeds_file_size_limit(best_photo.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_build_file_too_large_message(deps.settings.max_file_size_mb))
        return

    session = _get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text(_build_session_file_limit_message(deps.settings.max_session_files))
        return
    if session.files and any(item.kind != FileKind.IMAGE for item in session.files):
        await message.reply_text(MIXED_SESSION_MESSAGE)
        return

    generated_name = f"foto_{len(session.files) + 1}.jpg"
    session.files.append(build_session_file(best_photo.file_id, generated_name, FileKind.IMAGE))
    session.touch()
    deps.session_store.save(session)

    _schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)


async def handle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    action = (query.data or "").removeprefix("action:")
    if action == SupportedAction.PDF_COMPRESS.value:
        await query.edit_message_text(
            "Hai scelto la compressione PDF. Seleziona il livello.",
            reply_markup=build_compression_keyboard(),
        )
        return

    if action == SupportedAction.PDF_ROTATE.value:
        await query.edit_message_text(
            "La rotazione dei PDF ora avviene automaticamente quando serve. Quando la applico, ti offro anche un pulsante per rifare il file senza rotazione automatica."
        )
        return

    if _is_image_pdf_action(SupportedAction(action)):
        await query.edit_message_text(
            "Vuoi che impagini il PDF in formato A4?",
            reply_markup=build_images_pdf_layout_keyboard(action),
        )
        return

    if not _has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return

    supported_action = SupportedAction(action)
    job = await _enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=supported_action,
        session=session,
    )
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        f"Operazione presa in carico. Job #{job.id} in coda.\nTi scrivo qui appena ho finito."
    )


async def handle_compression_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()
    preset = (query.data or "").removeprefix("compress:")
    user = query.from_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)
    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    if not _has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return

    job = await _enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=SupportedAction.PDF_COMPRESS,
        session=session,
        compression_preset=CompressionPreset(preset),
    )
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        f"Compressione presa in carico. Job #{job.id} in coda.\nTi invio il PDF appena è pronto."
    )


async def handle_result_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await query.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    document = query.message.document
    if document is None or _infer_document_kind(document) != FileKind.PDF:
        await query.message.reply_text(
            "Non riesco più a recuperare questo PDF. Inviamelo di nuovo e lo converto subito.",
            reply_to_message_id=query.message.message_id,
        )
        return

    action = (query.data or "").removeprefix("result:")
    if action.startswith("undo_rotate:"):
        if not _has_capacity_for_new_job(user.id, deps):
            await query.message.reply_text(
                _build_job_queue_limit_message(deps.settings.max_active_jobs_per_user),
                reply_to_message_id=query.message.message_id,
            )
            return
        source_job_id = int(action.removeprefix("undo_rotate:"))
        source_job = deps.session_store.get_job(source_job_id)
        if source_job is None or source_job.user_id != user.id:
            await query.message.reply_text(
                "Non riesco più a recuperare l'operazione originale. Inviami di nuovo i file e la rifaccio senza rotazione automatica.",
                reply_to_message_id=query.message.message_id,
            )
            return

        rerun_job = await _enqueue_job_from_existing_payload(
            context=context,
            source_job=source_job,
            reply_to_message_id=query.message.message_id,
            auto_rotate_pdf=False,
        )
        await query.message.reply_text(
            _build_rerun_without_rotation_message(source_job, rerun_job.id),
            reply_to_message_id=query.message.message_id,
        )
        return

    if not _has_capacity_for_new_job(user.id, deps):
        await query.message.reply_text(
            _build_job_queue_limit_message(deps.settings.max_active_jobs_per_user),
            reply_to_message_id=query.message.message_id,
        )
        return

    if action != SupportedAction.PDF_GRAYSCALE.value:
        await query.message.reply_text(
            "Questa azione sul risultato non è supportata.",
            reply_to_message_id=query.message.message_id,
        )
        return

    session = UserSession(
        user_id=user.id,
        files=[build_session_file(document.file_id, document.file_name, FileKind.PDF)],
    )
    job = await _enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=SupportedAction.PDF_GRAYSCALE,
        session=session,
    )
    await query.message.reply_text(
        f"Conversione in scala di grigi presa in carico. Job #{job.id} in coda.\nTi invio il PDF appena è pronto.",
        reply_to_message_id=query.message.message_id,
    )


async def handle_images_pdf_layout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    _, layout_choice, action_name = (query.data or "").split(":", 2)
    action = SupportedAction(action_name)
    if not _is_image_pdf_action(action):
        await query.edit_message_text("Questa opzione non è supportata per il PDF richiesto.")
        return

    if layout_choice == "a4":
        await query.edit_message_text(
            "Che bordi vuoi nell'impaginazione A4?",
            reply_markup=build_images_pdf_margin_keyboard(action.value),
        )
        return

    if layout_choice != "original":
        await query.edit_message_text("Scelta non valida.")
        return

    await _enqueue_image_pdf_job_from_callback(
        query=query,
        context=context,
        user_id=user.id,
        action=action,
        session=session,
        image_pdf_use_a4=False,
        image_pdf_margin_px=A4_MARGIN_NONE_PX,
    )


async def handle_images_pdf_margin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    _, margin_choice, action_name = (query.data or "").split(":", 2)
    action = SupportedAction(action_name)
    margin_map = {
        "wide": A4_MARGIN_WIDE_PX,
        "narrow": A4_MARGIN_NARROW_PX,
        "none": A4_MARGIN_NONE_PX,
    }
    margin_px = margin_map.get(margin_choice)
    if margin_px is None:
        await query.edit_message_text("Scelta non valida.")
        return

    await _enqueue_image_pdf_job_from_callback(
        query=query,
        context=context,
        user_id=user.id,
        action=action,
        session=session,
        image_pdf_use_a4=True,
        image_pdf_margin_px=margin_px,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Errore non gestito", exc_info=context.error)


async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    message = update.effective_message
    if not _is_authorized(user.id if user else None, deps.settings):
        await message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    text = (message.text or "").strip()
    if text == "Mostra sessione":
        await status_command(update, context)
        return
    if text == "Azzera sessione":
        await reset_command(update, context)
        return
    if text == "Cosa posso fare":
        await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())
        return

    session = deps.session_store.get(user.id)
    if session is not None and session.files:
        inferred_request = _infer_text_requested_action(session, text)
        if inferred_request is not None:
            action, compression_preset = inferred_request
            if not _has_capacity_for_new_job(user.id, deps):
                await message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
                return

            if _is_image_pdf_action(action):
                await message.reply_text(
                    "Vuoi che impagini il PDF in formato A4?",
                    reply_markup=build_images_pdf_layout_keyboard(action.value),
                )
                return

            job = await _enqueue_job(
                context=context,
                user_id=user.id,
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
                action=action,
                session=session,
                compression_preset=compression_preset,
            )
            deps.session_store.delete(user.id)
            await message.reply_text(_build_text_request_queued_message(action, job.id, compression_preset))
            return

    quick_action_guidance = _build_quick_action_guidance(session, text)
    if quick_action_guidance is not None:
        await message.reply_text(quick_action_guidance, reply_markup=build_main_menu_keyboard())
        return

    await message.reply_text(
        "Per iniziare, inviami immagini o PDF. Se vuoi una guida rapida, usa /help.",
        reply_markup=build_main_menu_keyboard(),
    )


async def _maybe_notify_admins_about_new_user(user: User | None, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user is None:
        return

    deps = _get_dependencies(context)
    if not deps.settings.admin_user_ids:
        return

    is_new = deps.session_store.register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    if not is_new:
        return

    notification_text = _build_new_user_notification(user)
    for admin_user_id in deps.settings.admin_user_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_user_id,
                text=notification_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("Impossibile inviare la notifica nuovo utente all'admin %s", admin_user_id)


def _build_new_user_notification(user: User) -> str:
    timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M:%S")
    full_name = html.escape(user.full_name or "Sconosciuto")
    username = f"@{html.escape(user.username)}" if user.username else "non disponibile"
    profile_link = f'<a href="tg://user?id={user.id}">Apri profilo Telegram</a>'
    public_link = f' | <a href="https://t.me/{html.escape(user.username)}">Apri username</a>' if user.username else ""

    return (
        "Nuovo utente al primo accesso su <b>DocMolder</b>.\n"
        f"Data e ora: {timestamp}\n"
        f"ID utente: <code>{user.id}</code>\n"
        f"Nome: {full_name}\n"
        f"Username: {username}\n"
        f"Link: {profile_link}{public_link}"
    )


def _build_admin_report(
    stats: dict[str, int],
    top_users: list[AdminUserStat],
    failed_actions: list[AdminActionStat],
    recent_failed_jobs: list[JobRecord],
    recent_completed_jobs: list[JobRecord],
) -> str:
    timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M")
    total_finished_jobs = stats["jobs_succeeded"] + stats["jobs_failed"]
    success_rate = _format_percent(stats["jobs_succeeded"], total_finished_jobs)
    failure_rate = _format_percent(stats["jobs_failed"], total_finished_jobs)
    raster_share = _format_percent(stats["raster_results_total"], stats["jobs_succeeded"])
    top_users_block = "\n".join(
        f"- {entry.label} ({entry.user_id}): {entry.completed_actions} operazioni"
        for entry in top_users
    ) or "- Nessun dato ancora disponibile"
    failed_actions_block = "\n".join(
        f"- {_action_label(entry.action)}: {entry.total}"
        for entry in failed_actions
    ) or "- Nessun pattern di errore rilevante"
    failed_jobs_block = "\n".join(_format_job_line(job) for job in recent_failed_jobs) or "- Nessun job fallito di recente"
    completed_jobs_block = "\n".join(_format_job_line(job) for job in recent_completed_jobs) or "- Nessun job completato di recente"
    return (
        "Riepilogo admin DocMolder\n"
        f"Aggiornato: {timestamp}\n\n"
        f"Utenti unici totali: {stats['known_users_total']}\n"
        f"Nuovi utenti ultime 24 ore: {stats['known_users_last_24h']}\n"
        f"Nuovi utenti ultimi 7 giorni: {stats['known_users_last_7d']}\n"
        f"Operazioni completate totali: {stats['completed_actions_total']}\n"
        f"Operazioni completate ultime 24 ore: {stats['completed_actions_last_24h']}\n"
        f"Operazioni completate ultimi 7 giorni: {stats['completed_actions_last_7d']}\n"
        f"Sessioni attive ora: {stats['active_sessions']}\n\n"
        "Stato coda:\n"
        f"- In coda: {stats['jobs_queued']}\n"
        f"- In lavorazione: {stats['jobs_running']}\n"
        f"- Falliti: {stats['jobs_failed']}\n"
        f"- Completati: {stats['jobs_succeeded']}\n\n"
        "Metriche tecniche medie:\n"
        f"- Durata: {_format_duration_ms(stats['avg_duration_ms'])}\n"
        f"- Input: {_format_bytes(stats['avg_input_bytes'])}\n"
        f"- Output: {_format_bytes(stats['avg_output_bytes'])}\n"
        f"- Risultati con fallback raster: {stats['raster_results_total']} ({raster_share})\n\n"
        "Sintesi qualità:\n"
        f"- Job riusciti: {stats['jobs_succeeded']} ({success_rate})\n"
        f"- Job falliti: {stats['jobs_failed']} ({failure_rate})\n\n"
        "Dettaglio operazioni:\n"
        f"- PDF da immagini: {stats['images_to_pdf_total']}\n"
        f"- Comprimi PDF: {stats['pdf_compress_total']}\n"
        f"- Scala di grigi: {stats['pdf_grayscale_total']}\n"
        f"- Unisci PDF: {stats['pdf_merge_total']}\n"
        f"- Correggi orientamento: {stats['auto_orient_total']}\n\n"
        "Errori più frequenti ultimi 7 giorni:\n"
        f"{failed_actions_block}\n\n"
        "Utenti più attivi ultimi 7 giorni:\n"
        f"{top_users_block}\n\n"
        "Ultimi job completati:\n"
        f"{completed_jobs_block}\n\n"
        "Ultimi job falliti:\n"
        f"{failed_jobs_block}"
    )


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
    return f"{(value / total) * 100:.0f}%"


def _action_label(action: str) -> str:
    action_labels = {
        "images_to_pdf": "PDF da immagini",
        "images_to_pdf_crop": "PDF con ritaglio bordi",
        "images_to_pdf_grayscale": "PDF grigio da immagini",
        "images_to_pdf_crop_grayscale": "PDF grigio con ritaglio bordi",
        "pdf_compress": "Comprimi PDF",
        "pdf_grayscale": "Scala di grigi",
        "pdf_merge": "Unisci PDF",
        "auto_orient": "Correggi orientamento",
    }
    return action_labels.get(action, action)


def build_application(settings: Settings) -> Application:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        level=logging.INFO,
    )

    session_store = SQLiteSessionStore(settings.database_path)
    processor = DocumentProcessor(runtime_dir=settings.runtime_dir)
    deps = BotDependencies(settings=settings, session_store=session_store, processor=processor)

    application = (
        Application.builder()
        .token(settings.telegram_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.bot_data["deps"] = deps

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(handle_result_action_callback, pattern=r"^result:"))
    application.add_handler(CallbackQueryHandler(handle_compression_callback, pattern=r"^compress:"))
    application.add_handler(CallbackQueryHandler(handle_images_pdf_margin_callback, pattern=r"^images_pdf_margin:"))
    application.add_handler(CallbackQueryHandler(handle_images_pdf_layout_callback, pattern=r"^images_pdf_layout:"))
    application.add_handler(CallbackQueryHandler(handle_action_callback, pattern=r"^action:"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))
    application.add_error_handler(error_handler)

    return application


def _infer_document_kind(document: Document) -> FileKind | None:
    mime_type = document.mime_type or ""
    file_name = (document.file_name or "").lower()
    if mime_type == "application/pdf" or file_name.endswith(".pdf"):
        return FileKind.PDF
    if mime_type.startswith("image/") or file_name.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return FileKind.IMAGE
    return None


def _pick_best_photo(photos: list[PhotoSize]) -> PhotoSize:
    return max(photos, key=lambda item: item.file_size or 0)


def _exceeds_file_size_limit(file_size: int | None, max_file_size_mb: int) -> bool:
    if file_size is None:
        return False
    return file_size > max_file_size_mb * 1024 * 1024


def _build_file_too_large_message(max_file_size_mb: int) -> str:
    return f"{FILE_TOO_LARGE_MESSAGE} Limite attuale: {max_file_size_mb} MB."


def _build_session_file_limit_message(max_session_files: int) -> str:
    return (
        "Hai raggiunto il numero massimo di file per questa sessione. "
        f"Limite attuale: {max_session_files} file. Usa /reset per ricominciare."
    )


def _build_upload_rate_limit_message(upload_burst_limit: int, upload_burst_window_seconds: int) -> str:
    return (
        f"{UPLOAD_RATE_LIMIT_MESSAGE} "
        f"Limite attuale: {upload_burst_limit} file in {upload_burst_window_seconds} secondi."
    )


def _build_job_queue_limit_message(max_active_jobs_per_user: int) -> str:
    return (
        f"{JOB_QUEUE_LIMIT_MESSAGE} "
        f"Limite attuale: {max_active_jobs_per_user} job attivi per utente."
    )


def _schedule_image_session_notification(
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    deps = _get_dependencies(context)
    _cancel_pending_image_notification(user_id, deps)
    task = asyncio.create_task(_send_image_session_notification(chat_id, user_id, context))
    deps.pending_image_notifications[user_id] = task


async def _send_image_session_notification(
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    deps = _get_dependencies(context)
    try:
        await asyncio.sleep(1.2)
        session = deps.session_store.get(user_id)
        if session is None or not session.files:
            return
        if {item.kind for item in session.files} != {FileKind.IMAGE}:
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=_build_image_session_message(session),
            reply_markup=_filter_keyboard_for_session(session),
        )
    except asyncio.CancelledError:
        raise
    finally:
        current_task = deps.pending_image_notifications.get(user_id)
        if current_task is asyncio.current_task():
            deps.pending_image_notifications.pop(user_id, None)


def _build_image_session_message(session: UserSession) -> str:
    image_count = sum(1 for item in session.files if item.kind == FileKind.IMAGE)
    if image_count == 1:
        return (
            "Immagine ricevuta.\n"
            "Puoi inviarmi altre immagini per creare un PDF unico scegliendo se impaginarlo in A4 oppure no, "
            "ritagliare automaticamente i bordi, oppure scegliere subito un'azione."
        )

    return (
        f"Ho ricevuto {image_count} immagini nella stessa sessione.\n"
        "Puoi creare un PDF unico scegliendo se impaginarlo in A4 oppure no, ritagliare automaticamente i bordi oppure correggere l'orientamento."
    )


def _normalize_free_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _contains_any(text: str, fragments: tuple[str, ...]) -> bool:
    return any(fragment in text for fragment in fragments)


def _infer_text_requested_action(
    session: UserSession,
    text: str,
) -> tuple[SupportedAction, CompressionPreset | None] | None:
    normalized = _normalize_free_text(text)
    supported = set(infer_supported_actions(session))

    wants_grayscale = _contains_any(
        normalized,
        ("scala di grigi", "bianco e nero", "bianco nero", "grayscale", "grigio"),
    )
    wants_pdf = _contains_any(normalized, ("pdf", "documento"))
    wants_crop = _contains_any(normalized, ("ritaglia", "ritaglio", "bordi", "margini", "scannerizzato", "scansionato"))
    wants_merge = _contains_any(normalized, ("unisci", "accorpa", "merge"))
    wants_compress = _contains_any(normalized, ("comprimi", "compressione", "alleggerisci", "riduci"))
    wants_orient = _contains_any(normalized, ("orientamento", "raddrizza", "raddrizzare"))

    if SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE in supported and wants_crop and wants_grayscale:
        return SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE, None
    if SupportedAction.IMAGES_TO_PDF_CROP in supported and wants_crop and wants_pdf:
        return SupportedAction.IMAGES_TO_PDF_CROP, None
    if SupportedAction.PDF_MERGE in supported and wants_merge:
        return SupportedAction.PDF_MERGE, None
    if SupportedAction.PDF_COMPRESS in supported and wants_compress:
        return SupportedAction.PDF_COMPRESS, CompressionPreset.MEDIUM
    if SupportedAction.PDF_GRAYSCALE in supported and wants_grayscale:
        return SupportedAction.PDF_GRAYSCALE, None
    if SupportedAction.AUTO_ORIENT in supported and wants_orient:
        return SupportedAction.AUTO_ORIENT, None
    if SupportedAction.IMAGES_TO_PDF_GRAYSCALE in supported and wants_grayscale:
        return SupportedAction.IMAGES_TO_PDF_GRAYSCALE, None
    if SupportedAction.IMAGES_TO_PDF in supported and wants_pdf:
        return SupportedAction.IMAGES_TO_PDF, None
    return None


def _build_text_request_queued_message(
    action: SupportedAction,
    job_id: int,
    compression_preset: CompressionPreset | None,
) -> str:
    if action == SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE:
        return (
            f"Ritaglio automatico e PDF in scala di grigi presi in carico. "
            f"Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
        )
    if action == SupportedAction.IMAGES_TO_PDF_CROP:
        return f"Ritaglio automatico e creazione PDF presi in carico. Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
    if action == SupportedAction.IMAGES_TO_PDF_GRAYSCALE:
        return f"PDF in scala di grigi preso in carico. Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
    if action == SupportedAction.IMAGES_TO_PDF:
        return f"Creazione PDF presa in carico. Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
    if action == SupportedAction.PDF_GRAYSCALE:
        return (
            f"Conversione in scala di grigi presa in carico. Job #{job_id} in coda.\n"
            "Se il PDF è complesso potrei impiegare un po' di più o usare un fallback per garantirti comunque un risultato."
        )
    if action == SupportedAction.PDF_MERGE:
        return f"Unione PDF presa in carico. Job #{job_id} in coda.\nTi invio il file appena è pronto."
    if action == SupportedAction.PDF_COMPRESS:
        preset_label = (compression_preset or CompressionPreset.MEDIUM).value
        extra_note = (
            "\nSe il PDF è difficile da comprimere potrei impiegare più tempo o usare un fallback compatibile."
            if preset_label in {CompressionPreset.MEDIUM.value, CompressionPreset.STRONG.value}
            else ""
        )
        return (
            f"Compressione PDF presa in carico con livello {preset_label}. "
            f"Job #{job_id} in coda.\nTi invio il file appena è pronto.{extra_note}"
        )
    if action == SupportedAction.AUTO_ORIENT:
        return f"Correzione orientamento presa in carico. Job #{job_id} in coda.\nTi invio il risultato appena è pronto."
    return f"Operazione presa in carico. Job #{job_id} in coda."


def _build_rerun_without_rotation_message(source_job: JobRecord, job_id: int) -> str:
    payload = json.loads(source_job.payload_json)
    action = SupportedAction(source_job.action)
    compression_preset = CompressionPreset(payload["compression_preset"]) if payload.get("compression_preset") else None
    base_message = _build_text_request_queued_message(action, job_id, compression_preset)
    return f"Ripeto la stessa operazione senza rotazione automatica del PDF.\n{base_message}"


def _build_processing_started_message(action: SupportedAction, job_id: int) -> str:
    if action == SupportedAction.PDF_GRAYSCALE:
        return (
            f"Sto elaborando i file. Potrebbe volerci qualche secondo.\n"
            f"Job #{job_id} in elaborazione.\n"
            "Se il PDF non si lascia convertire bene in modo nativo, proverò una soluzione di ripiego compatibile."
        )
    if action == SupportedAction.PDF_COMPRESS:
        return (
            f"Sto elaborando i file. Potrebbe volerci qualche secondo.\n"
            f"Job #{job_id} in elaborazione.\n"
            "Nei casi più difficili la compressione può richiedere un po' di più per trovare il fallback più adatto."
        )
    return f"{PROCESSING_MESSAGE}\nJob #{job_id} in elaborazione."


def _build_quick_action_guidance(session: UserSession | None, text: str) -> str | None:
    if text == "Crea PDF da immagini":
        if session is None or not session.files:
            return "Inviami una o piu immagini e creerò un PDF unico. Se vuoi, puoi mandarne diverse nella stessa sessione."
        if {item.kind for item in session.files} == {FileKind.PDF}:
            return "Per creare un PDF da immagini devo partire da foto o scansioni. Usa /reset e inviami una o piu immagini."

    if text == "Comprimi PDF":
        if session is None or not session.files:
            return "Inviami un PDF e potrò comprimerlo subito. Se ne mandi uno solo, ti proporrò anche i livelli di compressione."
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return "Per comprimere serve un PDF. Se vuoi, posso prima trasformare le immagini in un PDF."
        if len(session.files) > 1:
            return "Per comprimere serve un solo PDF nella sessione corrente. Inviamene uno solo oppure unisci prima i file."

    if text == "Unisci PDF":
        if session is None or not session.files:
            return "Inviami due o piu PDF nella stessa sessione e li unirò in un file unico."
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return "Per unire servono PDF, non immagini. Se vuoi, posso prima creare un PDF dalle immagini che hai inviato."
        if len(session.files) == 1:
            return "Per unire i PDF me ne servono almeno due nella stessa sessione."

    return None


async def _enqueue_job(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    action: SupportedAction,
    session: UserSession,
    compression_preset: CompressionPreset | None = None,
    rotate_degrees: int | None = None,
    auto_rotate_pdf: bool = True,
    image_pdf_use_a4: bool = True,
    image_pdf_margin_px: int = A4_MARGIN_NARROW_PX,
) -> JobRecord:
    deps = _get_dependencies(context)
    if action not in infer_supported_actions(session):
        raise ProcessingUserError("L'azione scelta non è più disponibile per la sessione corrente.")
    payload = {
        "files": [
            {
                "telegram_file_id": item.telegram_file_id,
                "file_name": item.file_name,
                "kind": item.kind.value,
            }
            for item in session.files
        ],
        "compression_preset": compression_preset.value if compression_preset else None,
        "rotate_degrees": rotate_degrees,
        "auto_rotate_pdf": auto_rotate_pdf,
        "image_pdf_use_a4": image_pdf_use_a4,
        "image_pdf_margin_px": image_pdf_margin_px,
    }
    job = deps.session_store.create_job(
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=action.value,
        payload_json=json.dumps(payload),
    )
    await deps.job_queue.put(job.id)
    return job


async def _enqueue_job_from_existing_payload(
    context: ContextTypes.DEFAULT_TYPE,
    source_job: JobRecord,
    reply_to_message_id: int | None,
    *,
    auto_rotate_pdf: bool,
) -> JobRecord:
    deps = _get_dependencies(context)
    payload = json.loads(source_job.payload_json)
    payload["auto_rotate_pdf"] = auto_rotate_pdf
    job = deps.session_store.create_job(
        user_id=source_job.user_id,
        chat_id=source_job.chat_id,
        reply_to_message_id=reply_to_message_id,
        action=source_job.action,
        payload_json=json.dumps(payload),
    )
    await deps.job_queue.put(job.id)
    return job


async def _job_worker(application: Application) -> None:
    deps: BotDependencies = application.bot_data["deps"]
    while True:
        job_id = await deps.job_queue.get()
        try:
            await _process_job(application, job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Errore non gestito nel worker del job %s", job_id)
        finally:
            deps.job_queue.task_done()


async def _cleanup_worker(deps: BotDependencies) -> None:
    interval_seconds = max(60, deps.settings.cleanup_interval_minutes * 60)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            _run_cleanup_cycle(deps)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Errore durante il cleanup schedulato.")


async def _admin_report_worker(application: Application) -> None:
    deps: BotDependencies = application.bot_data["deps"]
    while True:
        try:
            await asyncio.sleep(300)
            await _maybe_send_periodic_admin_reports(application, deps)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Errore durante l'invio dei report admin periodici.")


def _run_cleanup_cycle(deps: BotDependencies) -> None:
    removed_dirs = deps.processor.cleanup_stale_job_dirs(deps.settings.stale_job_retention_hours)
    if removed_dirs:
        logger.info("Cleanup schedulato: rimosse %s cartelle temporanee residue.", removed_dirs)


async def _maybe_send_periodic_admin_reports(application: Application, deps: BotDependencies) -> None:
    if not deps.settings.admin_user_ids:
        return

    now = datetime.now(ZoneInfo("Europe/Rome"))
    await _maybe_send_admin_report_for_period(
        application,
        deps,
        period="daily",
        report_date=now.date().isoformat(),
        should_send=now.hour >= deps.settings.admin_daily_report_hour,
        since_days=1,
        title="Riepilogo admin giornaliero DocMolder",
    )
    await _maybe_send_admin_report_for_period(
        application,
        deps,
        period="weekly",
        report_date=now.date().isoformat(),
        should_send=(
            now.weekday() == deps.settings.admin_weekly_report_day
            and now.hour >= deps.settings.admin_weekly_report_hour
        ),
        since_days=7,
        title="Riepilogo admin settimanale DocMolder",
    )


async def _maybe_send_admin_report_for_period(
    application: Application,
    deps: BotDependencies,
    *,
    period: str,
    report_date: str,
    should_send: bool,
    since_days: int,
    title: str,
) -> None:
    if not should_send:
        return
    meta_key = f"admin_report_{period}_last_sent"
    if deps.session_store.get_meta(meta_key) == report_date:
        return
    report_text = _build_periodic_admin_report(deps, since_days=since_days, title=title)
    for admin_user_id in deps.settings.admin_user_ids:
        await application.bot.send_message(chat_id=admin_user_id, text=report_text)
    deps.session_store.set_meta(meta_key, report_date)


def _build_periodic_admin_report(deps: BotDependencies, *, since_days: int, title: str) -> str:
    stats = deps.session_store.build_admin_stats()
    top_users = deps.session_store.list_top_users(limit=5, since_days=since_days)
    failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=since_days)
    recent_failed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
    recent_completed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))
    return f"{title}\n\n{_build_admin_report(stats, top_users, failed_actions, recent_failed_jobs, recent_completed_jobs)}"


async def _process_job(application: Application, job_id: int) -> None:
    deps: BotDependencies = application.bot_data["deps"]
    job = deps.session_store.get_job(job_id)
    if job is None:
        return

    deps.session_store.mark_job_running(job_id)
    job = deps.session_store.get_job(job_id)
    if job is None:
        return

    await application.bot.send_message(
        chat_id=job.chat_id,
        text=_build_processing_started_message(SupportedAction(job.action), job.id),
        reply_to_message_id=job.reply_to_message_id,
    )

    job_dir = deps.processor.create_job_dir(job.user_id)
    started_monotonic = perf_counter()
    try:
        result = await _run_job_payload(application, job, job_dir)
    except ProcessingUserError as exc:
        deps.session_store.mark_job_failed(job.id, str(exc))
        await application.bot.send_message(
            chat_id=job.chat_id,
            text=f"Job #{job.id} non riuscito.\n{exc}",
            reply_to_message_id=job.reply_to_message_id,
        )
        return
    except Exception:
        logger.exception("Errore durante il job %s", job.id)
        deps.session_store.mark_job_failed(job.id, GENERIC_ERROR_MESSAGE)
        await application.bot.send_message(
            chat_id=job.chat_id,
            text=f"Job #{job.id} non riuscito.\n{GENERIC_ERROR_MESSAGE}",
            reply_to_message_id=job.reply_to_message_id,
        )
        return

    input_dir = job_dir / "input"
    input_bytes = _sum_file_sizes(input_dir.iterdir()) if input_dir.exists() else 0
    output_bytes = result.output_path.stat().st_size if result.output_path.exists() else 0
    duration_ms = int((perf_counter() - started_monotonic) * 1000)
    deps.session_store.mark_job_succeeded_with_metrics(
        job.id,
        result.message,
        processing_mode=result.processing_mode,
        input_bytes=input_bytes,
        output_bytes=output_bytes,
        duration_ms=duration_ms,
    )
    deps.session_store.record_completed_action(job.user_id, job.action)
    try:
        await _send_result(application.bot, job.chat_id, job.reply_to_message_id, result, source_job_id=job.id)
    finally:
        deps.processor.cleanup_job_dir(job_dir)


async def _run_job_payload(
    application: Application,
    job: JobRecord,
    job_dir: Path,
) -> ProcessingResult:
    deps: BotDependencies = application.bot_data["deps"]
    payload = json.loads(job.payload_json)
    session = UserSession(
        user_id=job.user_id,
        files=[
            build_session_file(
                file_id=item["telegram_file_id"],
                file_name=item["file_name"],
                kind=FileKind(item["kind"]),
            )
            for item in payload["files"]
        ],
    )

    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    downloaded_paths = await _download_session_files(application, session, input_dir)

    result = await asyncio.to_thread(
        deps.processor.process,
        SupportedAction(job.action),
        downloaded_paths,
        build_output_stem(SupportedAction(job.action)),
        CompressionPreset(payload["compression_preset"]) if payload.get("compression_preset") else None,
        payload.get("rotate_degrees"),
        payload.get("auto_rotate_pdf", True),
        payload.get("image_pdf_use_a4", True),
        payload.get("image_pdf_margin_px", A4_MARGIN_NARROW_PX),
    )
    return result


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
    deps = _get_dependencies(context)
    if not _has_capacity_for_new_job(user_id, deps):
        await query.edit_message_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return

    job = await _enqueue_job(
        context=context,
        user_id=user_id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=action,
        session=session,
        image_pdf_use_a4=image_pdf_use_a4,
        image_pdf_margin_px=image_pdf_margin_px,
    )
    deps.session_store.delete(user_id)
    await query.edit_message_text(
        f"{_describe_image_pdf_choice(image_pdf_use_a4, image_pdf_margin_px)}\n"
        f"{_build_text_request_queued_message(action, job.id, None)}"
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


async def _download_session_files(
    application: Application,
    session: UserSession,
    input_dir: Path,
) -> list[Path]:
    downloaded_paths: list[Path] = []
    for index, session_file in enumerate(session.files, start=1):
        telegram_file = await application.bot.get_file(session_file.telegram_file_id)
        file_name = sanitize_filename(session_file.file_name)
        target_path = input_dir / f"{index:02d}_{file_name}"
        await telegram_file.download_to_drive(custom_path=str(target_path))
        downloaded_paths.append(target_path)
    return downloaded_paths


async def _send_result(
    bot,
    chat_id: int,
    reply_to_message_id: int | None,
    result: ProcessingResult,
    *,
    source_job_id: int | None = None,
) -> None:
    with result.output_path.open("rb") as payload:
        await bot.send_document(
            chat_id=chat_id,
            document=payload,
            filename=result.output_name,
            caption=result.message,
            reply_to_message_id=reply_to_message_id,
            reply_markup=(
                build_result_pdf_keyboard(
                    undo_rotation_job_id=source_job_id if result.auto_rotation_applied else None,
                )
                if result.output_name.lower().endswith(".pdf")
                else None
            ),
        )


def _sum_file_sizes(paths) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total
