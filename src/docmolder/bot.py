from __future__ import annotations

import asyncio
import html
import logging
import re
import unicodedata
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
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
    build_rotate_keyboard,
    build_result_pdf_keyboard,
)
from docmolder.job_flow import (
    enqueue_job as enqueue_job_flow,
    enqueue_job_from_existing_payload as enqueue_job_from_existing_payload_flow,
    run_job_payload as run_job_payload_flow,
)
from docmolder.messages import (
    FILE_TOO_LARGE_MESSAGE,
    GENERIC_ERROR_MESSAGE,
    HELP_MESSAGE,
    JOB_QUEUE_LIMIT_MESSAGE,
    SESSION_EMPTY_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    UPLOAD_RATE_LIMIT_MESSAGE,
    build_pending_action_prompt,
    build_pending_action_queued_message,
    build_processing_started_message,
    build_text_request_queued_message,
)
from docmolder.models import AdminActionStat, AdminStats, AdminUserStat, CompressionPreset, FileKind, JobPayload, JobRecord, JobStatus, SupportedAction, UserSession
from docmolder.processing import (
    A4_MARGIN_NARROW_PX,
    A4_MARGIN_NONE_PX,
    A4_MARGIN_WIDE_PX,
    DocumentProcessor,
    ProcessingResult,
    ProcessingUserError,
)
from docmolder.services import (
    build_session_file,
    build_session_recap,
    get_action_label,
    infer_exposed_actions,
    infer_result_followup_actions,
    infer_supported_actions,
    sanitize_filename,
)
from docmolder.session_store import SQLiteSessionStore, SessionStore

logger = logging.getLogger(__name__)

_TELEGRAM_TOKEN_IN_URL_RE = re.compile(r"/bot[^/]+/")

_build_pending_action_prompt = build_pending_action_prompt
_build_pending_action_queued_message = build_pending_action_queued_message
_build_processing_started_message = build_processing_started_message
_build_text_request_queued_message = build_text_request_queued_message

_PENDING_IMAGES_PDF_LAYOUT_PREFIX = "images_pdf_layout"
_PENDING_IMAGES_PDF_MARGIN_PREFIX = "images_pdf_margin"


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


class SensitiveLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_sensitive_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_sensitive_arg(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact_sensitive_arg(value) for key, value in record.args.items()}
        return True


def _redact_sensitive_arg(value: object) -> object:
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def _redact_sensitive_text(text: str) -> str:
    return _TELEGRAM_TOKEN_IN_URL_RE.sub("/bot<redacted>/", text)


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        level=logging.INFO,
    )
    sensitive_filter = SensitiveLogFilter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(sensitive_filter)

    # Reduce request/response chatter from the Telegram HTTP client and avoid
    # leaking full URLs with the bot token into service logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


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


async def _enqueue_job(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    action: SupportedAction,
    session: UserSession,
    compression_preset: CompressionPreset | None = None,
    rotate_degrees: int | None = None,
    page_selection: str | None = None,
    watermark_text: str | None = None,
    auto_rotate_pdf: bool = True,
    image_pdf_use_a4: bool = True,
    image_pdf_margin_px: int = A4_MARGIN_NARROW_PX,
) -> JobRecord:
    deps = _get_dependencies(context)
    return await enqueue_job_flow(
        deps=deps,
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=action,
        session=session,
        compression_preset=compression_preset,
        rotate_degrees=rotate_degrees,
        page_selection=page_selection,
        watermark_text=watermark_text,
        auto_rotate_pdf=auto_rotate_pdf,
        image_pdf_use_a4=image_pdf_use_a4,
        image_pdf_margin_px=image_pdf_margin_px,
    )


async def _enqueue_job_from_existing_payload(
    context: ContextTypes.DEFAULT_TYPE,
    source_job: JobRecord,
    reply_to_message_id: int | None,
    *,
    auto_rotate_pdf: bool | None = None,
) -> JobRecord:
    deps = _get_dependencies(context)
    return await enqueue_job_from_existing_payload_flow(
        deps=deps,
        source_job=source_job,
        reply_to_message_id=reply_to_message_id,
        auto_rotate_pdf=auto_rotate_pdf,
    )


async def _run_job_payload(
    application: Application,
    job: JobRecord,
    job_dir: Path,
) -> ProcessingResult:
    deps: BotDependencies = application.bot_data["deps"]
    return await run_job_payload_flow(
        application=application,
        processor=deps.processor,
        job=job,
        job_dir=job_dir,
        download_session_files=_download_session_files,
    )


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
    return build_actions_keyboard(infer_exposed_actions(session))


def _is_image_pdf_action(action: SupportedAction) -> bool:
    return action in {
        SupportedAction.IMAGES_TO_PDF,
        SupportedAction.IMAGES_TO_PDF_CROP,
        SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
        SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
    }


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import start_command as delegated_handler

    await delegated_handler(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import help_command as delegated_handler

    await delegated_handler(update, context)


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import history_command as delegated_handler

    await delegated_handler(update, context)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import admin_command as delegated_handler

    await delegated_handler(update, context)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import reset_command as delegated_handler

    await delegated_handler(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import status_command as delegated_handler

    await delegated_handler(update, context)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import handle_document as delegated_handler

    await delegated_handler(update, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from docmolder.handlers import handle_photo as delegated_handler

    await delegated_handler(update, context)


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
            _build_compression_prompt(user.id, deps),
            reply_markup=build_compression_keyboard(),
        )
        return

    if action == SupportedAction.PDF_ROTATE.value:
        await query.edit_message_text(
            "Di quanti gradi vuoi ruotare tutte le pagine del PDF?",
            reply_markup=build_rotate_keyboard(),
        )
        return

    if action in {
        SupportedAction.PDF_EXTRACT_PAGES.value,
        SupportedAction.PDF_REORDER_PAGES.value,
        SupportedAction.PDF_DELETE_PAGES.value,
        SupportedAction.PDF_WATERMARK.value,
    }:
        session.pending_action = action
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(_build_pending_action_prompt(SupportedAction(action)))
        return

    if _is_image_pdf_action(SupportedAction(action)):
        await query.edit_message_text(
            _build_image_pdf_layout_prompt(user.id, deps),
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
    deps.session_store.set_user_preference(user.id, "compression_preset", preset)
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

    try:
        selected_action = SupportedAction(action)
    except ValueError:
        await query.message.reply_text(
            "Questa azione sul risultato non è supportata.",
            reply_to_message_id=query.message.message_id,
        )
        return

    session = _build_result_pdf_session(user.id, document.file_id, document.file_name)
    deps.session_store.save(session)

    if selected_action == SupportedAction.PDF_COMPRESS:
        await query.message.reply_text(
            _build_compression_prompt(user.id, deps),
            reply_to_message_id=query.message.message_id,
            reply_markup=build_compression_keyboard(),
        )
        return

    if selected_action == SupportedAction.PDF_ROTATE:
        await query.message.reply_text(
            "Di quanti gradi vuoi ruotare tutte le pagine del PDF?\nScelta rapida: tocca uno dei pulsanti qui sotto.",
            reply_to_message_id=query.message.message_id,
            reply_markup=build_rotate_keyboard(),
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
            _build_pending_action_prompt(selected_action),
            reply_to_message_id=query.message.message_id,
        )
        return

    job = await _enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=selected_action,
        session=session,
    )
    deps.session_store.delete(user.id)
    await query.message.reply_text(
        _build_text_request_queued_message(selected_action, job.id, None),
        reply_to_message_id=query.message.message_id,
    )


async def handle_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await query.message.reply_text(UNAUTHORIZED_MESSAGE, reply_to_message_id=query.message.message_id)
        return
    await _maybe_notify_admins_about_new_user(user, context)

    try:
        _, action, raw_job_id = (query.data or "").split(":", 2)
        job_id = int(raw_job_id)
    except (TypeError, ValueError):
        await query.message.reply_text("Richiesta non valida.", reply_to_message_id=query.message.message_id)
        return

    job = deps.session_store.get_job(job_id)
    if job is None or job.user_id != user.id:
        await query.message.reply_text(
            "Non riesco più a recuperare questo job dal tuo storico.",
            reply_to_message_id=query.message.message_id,
        )
        return

    if action == "details":
        await query.message.reply_text(
            _build_user_history_job_detail(job),
            reply_to_message_id=query.message.message_id,
        )
        return

    if action == "rerun":
        if not _has_capacity_for_new_job(user.id, deps):
            await query.message.reply_text(
                _build_job_queue_limit_message(deps.settings.max_active_jobs_per_user),
                reply_to_message_id=query.message.message_id,
            )
            return
        rerun_job = await _enqueue_job_from_existing_payload(
            context=context,
            source_job=job,
            reply_to_message_id=query.message.message_id,
        )
        await query.message.reply_text(
            _build_history_rerun_message(job, rerun_job.id),
            reply_to_message_id=query.message.message_id,
        )
        return

    await query.message.reply_text("Azione storico non supportata.", reply_to_message_id=query.message.message_id)


async def handle_rotate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    degrees = int((query.data or "").removeprefix("rotate:"))
    if not _has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return

    job = await _enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=SupportedAction.PDF_ROTATE,
        session=session,
        rotate_degrees=degrees,
    )
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        f"Rotazione manuale presa in carico di {degrees} gradi. Job #{job.id} in coda.\nTi invio il PDF appena è pronto."
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
    if text == "Storico lavori":
        await history_command(update, context)
        return
    if text == "Azzera sessione":
        await reset_command(update, context)
        return
    if text == "Cosa posso fare":
        await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())
        return

    session = deps.session_store.get(user.id)
    if session is not None and session.files:
        if session.pending_action is not None:
            handled = await _handle_pending_session_input(
                update=update,
                context=context,
                session=session,
                user_id=user.id,
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
                text=text,
            )
            if handled:
                return

        structured_request = _infer_structured_text_request(session, text)
        if structured_request is not None:
            action = structured_request["action"]
            if not _has_capacity_for_new_job(user.id, deps):
                await message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
                return

            job = await _enqueue_job(
                context=context,
                user_id=user.id,
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
                action=action,
                session=session,
                rotate_degrees=structured_request.get("rotate_degrees"),
                page_selection=structured_request.get("page_selection"),
                watermark_text=structured_request.get("watermark_text"),
            )
            deps.session_store.delete(user.id)
            if structured_request.get("page_selection") or structured_request.get("watermark_text"):
                raw_value = structured_request.get("page_selection") or structured_request.get("watermark_text") or ""
                await message.reply_text(_build_pending_action_queued_message(action, job.id, str(raw_value)))
            elif structured_request.get("rotate_degrees") is not None:
                await message.reply_text(
                    f"Rotazione manuale presa in carico di {structured_request['rotate_degrees']} gradi. "
                    f"Job #{job.id} in coda.\nTi invio il PDF appena è pronto."
                )
            else:
                await message.reply_text(_build_text_request_queued_message(action, job.id, None))
            return

        inferred_request = _infer_text_requested_action(session, text)
        if inferred_request is not None:
            action, compression_preset = inferred_request
            if not _has_capacity_for_new_job(user.id, deps):
                await message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
                return

            if _is_image_pdf_action(action):
                session.pending_action = _build_images_pdf_layout_pending_action(action)
                session.touch()
                deps.session_store.save(session)
                await message.reply_text(
                    _build_image_pdf_layout_prompt(user.id, deps),
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
    stats: AdminStats,
    top_users: list[AdminUserStat],
    failed_actions: list[AdminActionStat],
    recent_failed_jobs: list[JobRecord],
    recent_completed_jobs: list[JobRecord],
    *,
    activity_window_label: str = "ultimi 7 giorni",
    completed_jobs_heading: str = "Ultimi job completati",
    failed_jobs_heading: str = "Ultimi job falliti",
) -> str:
    timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M")
    total_finished_jobs = stats.jobs_succeeded + stats.jobs_failed
    success_rate = _format_percent(stats.jobs_succeeded, total_finished_jobs)
    failure_rate = _format_percent(stats.jobs_failed, total_finished_jobs)
    raster_share = _format_percent(stats.raster_results_total, stats.jobs_succeeded)
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
        f"Utenti unici totali: {stats.known_users_total}\n"
        f"Nuovi utenti ultime 24 ore: {stats.known_users_last_24h}\n"
        f"Nuovi utenti ultimi 7 giorni: {stats.known_users_last_7d}\n"
        f"Operazioni completate totali: {stats.completed_actions_total}\n"
        f"Operazioni completate ultime 24 ore: {stats.completed_actions_last_24h}\n"
        f"Operazioni completate ultimi 7 giorni: {stats.completed_actions_last_7d}\n"
        f"Sessioni attive ora: {stats.active_sessions}\n\n"
        "Stato coda:\n"
        f"- In coda: {stats.jobs_queued}\n"
        f"- In lavorazione: {stats.jobs_running}\n"
        f"- Falliti: {stats.jobs_failed}\n"
        f"- Completati: {stats.jobs_succeeded}\n\n"
        "Metriche tecniche medie:\n"
        f"- Durata: {_format_duration_ms(stats.avg_duration_ms)}\n"
        f"- Input: {_format_bytes(stats.avg_input_bytes)}\n"
        f"- Output: {_format_bytes(stats.avg_output_bytes)}\n"
        f"- Risultati con fallback raster: {stats.raster_results_total} ({raster_share})\n\n"
        "Sintesi qualità:\n"
        f"- Job riusciti: {stats.jobs_succeeded} ({success_rate})\n"
        f"- Job falliti: {stats.jobs_failed} ({failure_rate})\n\n"
        "Dettaglio operazioni:\n"
        f"- PDF da immagini: {stats.images_to_pdf_total}\n"
        f"- Comprimi PDF: {stats.pdf_compress_total}\n"
        f"- Scala di grigi: {stats.pdf_grayscale_total}\n"
        f"- Unisci PDF: {stats.pdf_merge_total}\n"
        f"- Estrai pagine: {stats.pdf_extract_pages_total}\n"
        f"- Riordina pagine: {stats.pdf_reorder_pages_total}\n"
        f"- Elimina pagine: {stats.pdf_delete_pages_total}\n"
        f"- Ruota pagine: {stats.pdf_rotate_total}\n"
        f"- Watermark: {stats.pdf_watermark_total}\n"
        f"- Correggi orientamento: {stats.auto_orient_total}\n\n"
        f"Errori più frequenti {activity_window_label}:\n"
        f"{failed_actions_block}\n\n"
        f"Utenti più attivi {activity_window_label}:\n"
        f"{top_users_block}\n\n"
        f"{completed_jobs_heading}:\n"
        f"{completed_jobs_block}\n\n"
        f"{failed_jobs_heading}:\n"
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
    return get_action_label(action)


def build_application(settings: Settings) -> Application:
    _configure_logging()

    session_store = SQLiteSessionStore(settings.database_path)
    processor = DocumentProcessor(
        runtime_dir=settings.runtime_dir,
        ghostscript_timeout_seconds=settings.ghostscript_timeout_seconds,
    )
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
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(handle_history_callback, pattern=r"^history:"))
    application.add_handler(CallbackQueryHandler(handle_rotate_callback, pattern=r"^rotate:"))
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


def _build_user_history_summary(jobs: list[JobRecord]) -> str:
    lines = [
        "Storico ultimi job",
        "",
        "Qui sotto trovi gli ultimi lavori raggruppati per stato e rilancio. Puoi aprire i dettagli o rilanciare un job.",
        "",
    ]
    grouped_jobs = [
        ("Rilanciati", [job for job in jobs if job.rerun_of_job_id is not None]),
        ("In lavorazione", [job for job in jobs if job.status in {JobStatus.QUEUED, JobStatus.RUNNING} and job.rerun_of_job_id is None]),
        ("Riusciti", [job for job in jobs if job.status == JobStatus.SUCCEEDED and job.rerun_of_job_id is None]),
        ("Falliti", [job for job in jobs if job.status == JobStatus.FAILED and job.rerun_of_job_id is None]),
    ]
    for heading, grouped in grouped_jobs:
        if not grouped:
            continue
        lines.append(f"{heading}:")
        lines.extend(_format_user_history_line(job) for job in grouped)
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
    file_count = len(payload.files)
    reference_time = (job.finished_at or job.created_at).astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")
    detail_lines = [
        f"Dettaglio Job #{job.id}",
        f"Azione: {_action_label(job.action)}",
        f"Stato: {_format_job_status(job.status)}",
        f"Riferimento temporale: {reference_time}",
        f"File sorgente: {file_count}",
    ]
    if job.rerun_of_job_id is not None:
        detail_lines.append(f"Origine rilancio: job #{job.rerun_of_job_id}")
    if payload.compression_preset:
        detail_lines.append(f"Compressione: {payload.compression_preset.value}")
    if payload.page_selection:
        detail_lines.append(f"Selezione pagine: {payload.page_selection}")
    if payload.image_pdf_use_a4 is not None and job.action.startswith("images_to_pdf"):
        detail_lines.append("Impaginazione: A4" if payload.image_pdf_use_a4 else "Impaginazione: formato originale")
    if payload.auto_rotate_pdf is not None:
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


def _build_history_rerun_message(source_job: JobRecord, job_id: int) -> str:
    payload = JobPayload.from_json(source_job.payload_json)
    base_message = _build_text_request_queued_message(
        SupportedAction(source_job.action),
        job_id,
        payload.compression_preset,
    )
    return f"Ripeto il job #{source_job.id} dal tuo storico.\n{base_message}"


def _format_job_status(status: JobStatus) -> str:
    return {
        JobStatus.QUEUED: "In coda",
        JobStatus.RUNNING: "In lavorazione",
        JobStatus.SUCCEEDED: "Completato",
        JobStatus.FAILED: "Fallito",
    }[status]


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
        intro = "Immagine ricevuta."
    else:
        intro = f"Ho ricevuto {image_count} immagini nella stessa sessione."
    return f"{intro}\n{build_session_recap(session)}"


def _build_result_pdf_session(user_id: int, file_id: str, file_name: str | None) -> UserSession:
    return UserSession(
        user_id=user_id,
        files=[build_session_file(file_id, file_name, FileKind.PDF)],
    )


def _build_compression_prompt(user_id: int, deps: BotDependencies) -> str:
    saved_preset = deps.session_store.get_user_preference(user_id, "compression_preset")
    saved_note = f"\nUltima scelta rapida salvata: {saved_preset}." if saved_preset else ""
    return (
        "Hai scelto la compressione PDF. Seleziona il livello.\n"
        "Leggera preserva di piu il file; Media e Forte cercano una riduzione piu evidente."
        f"{saved_note}"
    )


def _build_image_pdf_layout_prompt(user_id: int, deps: BotDependencies) -> str:
    saved_layout = deps.session_store.get_user_preference(user_id, "image_pdf_layout")
    saved_margin = deps.session_store.get_user_preference(user_id, "image_pdf_margin_px")
    saved_note = ""
    if saved_layout == "original":
        saved_note = "\nUltima scelta rapida salvata: formato originale."
    elif saved_layout == "a4":
        saved_note = "\nUltima scelta rapida salvata: A4"
        if saved_margin == str(A4_MARGIN_WIDE_PX):
            saved_note += " con bordi larghi."
        elif saved_margin == str(A4_MARGIN_NONE_PX):
            saved_note += " senza bordi."
        else:
            saved_note += " con bordi stretti."
    return f"Vuoi che impagini il PDF in formato A4?{saved_note}"


def _build_result_delivery_message(result: ProcessingResult, source_action: SupportedAction | None) -> str:
    if not result.output_name.lower().endswith(".pdf"):
        return result.message

    followup_actions = infer_result_followup_actions(source_action)
    if not followup_actions:
        return result.message

    quick_labels = ", ".join(get_action_label(action) for action in followup_actions[:3])
    return f"{result.message}\n\nSe vuoi, puoi continuare su questo PDF con: {quick_labels}."


def _build_result_followup_keyboard(
    result: ProcessingResult,
    source_action: SupportedAction | None,
    source_job_id: int | None,
) -> InlineKeyboardMarkup | None:
    if not result.output_name.lower().endswith(".pdf"):
        return None
    return build_result_pdf_keyboard(
        quick_actions=infer_result_followup_actions(source_action),
        undo_rotation_job_id=source_job_id if result.auto_rotation_applied else None,
    )


def _normalize_free_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


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
    deps = _get_dependencies(context)
    if session.pending_action is None:
        return False

    if session.pending_action.startswith(f"{_PENDING_IMAGES_PDF_LAYOUT_PREFIX}:"):
        return await _handle_pending_images_pdf_layout_input(
            update=update,
            context=context,
            session=session,
            user_id=user_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            text=text,
        )

    if session.pending_action.startswith(f"{_PENDING_IMAGES_PDF_MARGIN_PREFIX}:"):
        return await _handle_pending_images_pdf_margin_input(
            update=update,
            context=context,
            session=session,
            user_id=user_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            text=text,
        )

    pending_action = SupportedAction(session.pending_action)
    if not _has_capacity_for_new_job(user_id, deps):
        await update.effective_message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return True

    try:
        enqueue_kwargs: dict[str, object] = {}
        if pending_action in {
            SupportedAction.PDF_EXTRACT_PAGES,
            SupportedAction.PDF_REORDER_PAGES,
            SupportedAction.PDF_DELETE_PAGES,
        }:
            normalized_page_selection = _normalize_page_selection_text(text)
            _validate_page_input_text(normalized_page_selection)
            enqueue_kwargs["page_selection"] = normalized_page_selection
        elif pending_action == SupportedAction.PDF_WATERMARK:
            watermark_text = text.strip()
            if not watermark_text:
                await update.effective_message.reply_text(
                    "Il watermark testuale non puo essere vuoto. Scrivimi una parola o una frase breve, ad esempio BOZZA."
                )
                return True
            enqueue_kwargs["watermark_text"] = watermark_text
        else:
            return False

        job = await _enqueue_job(
            context=context,
            user_id=user_id,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            action=pending_action,
            session=session,
            **enqueue_kwargs,
        )
    except ProcessingUserError as exc:
        await update.effective_message.reply_text(
            f"{exc}\n\n{_build_pending_action_prompt(pending_action)}"
        )
        return True

    deps.session_store.delete(user_id)
    raw_value = enqueue_kwargs.get("page_selection") or enqueue_kwargs.get("watermark_text") or text
    await update.effective_message.reply_text(_build_pending_action_queued_message(pending_action, job.id, str(raw_value)))
    return True


def _build_images_pdf_layout_pending_action(action: SupportedAction) -> str:
    return f"{_PENDING_IMAGES_PDF_LAYOUT_PREFIX}:{action.value}"


def _build_images_pdf_margin_pending_action(action: SupportedAction) -> str:
    return f"{_PENDING_IMAGES_PDF_MARGIN_PREFIX}:{action.value}"


def _extract_pending_images_pdf_action(pending_action: str, prefix: str) -> SupportedAction | None:
    if not pending_action.startswith(f"{prefix}:"):
        return None
    raw_action = pending_action.split(":", 1)[1]
    try:
        action = SupportedAction(raw_action)
    except ValueError:
        return None
    if not _is_image_pdf_action(action):
        return None
    return action


def _parse_image_pdf_layout_choice(text: str) -> bool | None:
    normalized = _normalize_free_text(text)
    wants_a4 = "a4" in normalized and _contains_any(normalized, ("si", "sì", "impagina", "usa"))
    wants_original = _contains_any(
        normalized,
        ("mantieni formato originale", "formato originale", "originale", "non impaginare", "no a4"),
    ) or ("no" in normalized and "a4" in normalized)
    if wants_a4:
        return True
    if wants_original:
        return False
    return None


def _parse_image_pdf_margin_choice(text: str) -> int | None:
    normalized = _normalize_free_text(text)
    if _contains_any(normalized, ("senza bordi", "nessun bordo", "nessuno", "no bordi")):
        return A4_MARGIN_NONE_PX
    if _contains_any(normalized, ("bordi larghi", "bordi ampi", "larghi", "ampi")):
        return A4_MARGIN_WIDE_PX
    if _contains_any(normalized, ("bordi stretti", "stretto", "stretti", "narrow")):
        return A4_MARGIN_NARROW_PX
    return None


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
    deps = _get_dependencies(context)
    action = _extract_pending_images_pdf_action(session.pending_action or "", _PENDING_IMAGES_PDF_LAYOUT_PREFIX)
    if action is None:
        return False

    use_a4 = _parse_image_pdf_layout_choice(text)
    if use_a4 is None:
        await update.effective_message.reply_text(
            "Dimmi se vuoi il PDF in A4 oppure nel formato originale.\n"
            "Puoi scrivere ad esempio `Si, impagina in A4` oppure `No, mantieni formato originale`."
        )
        return True

    if use_a4:
        session.pending_action = _build_images_pdf_margin_pending_action(action)
        session.touch()
        deps.session_store.save(session)
        await update.effective_message.reply_text(
            "Che bordi vuoi nell'impaginazione A4?\n"
            "Puoi scrivere ad esempio `bordi stretti`, `bordi larghi` oppure `senza bordi`.",
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
    action = _extract_pending_images_pdf_action(session.pending_action or "", _PENDING_IMAGES_PDF_MARGIN_PREFIX)
    if action is None:
        return False

    margin_px = _parse_image_pdf_margin_choice(text)
    if margin_px is None:
        await update.effective_message.reply_text(
            "Dimmi che bordi vuoi in A4.\n"
            "Puoi scrivere `bordi stretti`, `bordi larghi` oppure `senza bordi`."
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
    deps = _get_dependencies(context)
    if not _has_capacity_for_new_job(user_id, deps):
        await update.effective_message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return True

    job = await _enqueue_job(
        context=context,
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=action,
        session=session,
        image_pdf_use_a4=image_pdf_use_a4,
        image_pdf_margin_px=image_pdf_margin_px,
    )
    deps.session_store.set_user_preference(user_id, "image_pdf_layout", "a4" if image_pdf_use_a4 else "original")
    deps.session_store.set_user_preference(user_id, "image_pdf_margin_px", str(image_pdf_margin_px))
    deps.session_store.delete(user_id)
    await update.effective_message.reply_text(
        f"{_describe_image_pdf_choice(image_pdf_use_a4, image_pdf_margin_px)}\n"
        f"{_build_text_request_queued_message(action, job.id, None)}"
    )
    return True


def _validate_page_input_text(text: str) -> None:
    value = text.strip()
    if not value:
        raise ProcessingUserError("Non ho ricevuto nessuna selezione pagine. Usa un formato come 1,3,5-7.")
    allowed_chars = set("0123456789,- ")
    if any(char not in allowed_chars for char in value):
        raise ProcessingUserError("Usa solo numeri, virgole e intervalli, ad esempio 1,3,5-7.")


def _normalize_page_selection_text(text: str) -> str:
    value = re.sub(r"(?<=\d)\s+(?=\d)", ",", text.strip())
    return re.sub(r"\s*,\s*", ",", value)


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


def _infer_structured_text_request(session: UserSession, text: str) -> dict[str, object] | None:
    normalized = _normalize_free_text(text)
    supported = set(infer_supported_actions(session))

    if SupportedAction.PDF_ROTATE in supported and _contains_any(normalized, ("ruota", "rotazione")):
        degrees = _extract_rotation_degrees(normalized)
        if degrees is not None:
            return {"action": SupportedAction.PDF_ROTATE, "rotate_degrees": degrees}

    if SupportedAction.PDF_EXTRACT_PAGES in supported and _contains_any(normalized, ("estrai", "estrazione")):
        page_selection = _extract_page_selection_from_text(normalized)
        if page_selection:
            return {"action": SupportedAction.PDF_EXTRACT_PAGES, "page_selection": page_selection}

    if SupportedAction.PDF_DELETE_PAGES in supported and _contains_any(normalized, ("elimina", "rimuovi", "cancella")):
        page_selection = _extract_page_selection_from_text(normalized)
        if page_selection:
            return {"action": SupportedAction.PDF_DELETE_PAGES, "page_selection": page_selection}

    if SupportedAction.PDF_REORDER_PAGES in supported and _contains_any(normalized, ("riordina", "riordinare", "ordina")):
        page_selection = _extract_page_selection_from_text(normalized, allow_keywordless_sequence=True)
        if page_selection:
            return {"action": SupportedAction.PDF_REORDER_PAGES, "page_selection": page_selection}

    if SupportedAction.PDF_WATERMARK in supported and "watermark" in normalized:
        watermark_text = _extract_watermark_text(text)
        if watermark_text:
            return {"action": SupportedAction.PDF_WATERMARK, "watermark_text": watermark_text}

    return None


def _extract_rotation_degrees(text: str) -> int | None:
    for degrees in (90, 180, 270):
        if str(degrees) in text:
            return degrees
    return None


def _extract_page_selection_from_text(text: str, *, allow_keywordless_sequence: bool = False) -> str | None:
    match = re.search(r"(?:pagina|pagine)\s+([0-9,\-\s]+)", text)
    if match:
        return _normalize_page_selection_text(match.group(1))
    if allow_keywordless_sequence:
        match = re.search(r"([0-9][0-9,\-\s]+)$", text.strip())
        if match:
            return _normalize_page_selection_text(match.group(1))
    return None


def _extract_watermark_text(text: str) -> str | None:
    match = re.search(r"watermark(?:\s+testuale)?[:\s]+(.+)$", text, flags=re.IGNORECASE)
    if match is None:
        return None
    watermark_text = match.group(1).strip().strip("\"'“”")
    return watermark_text or None


def _build_rerun_without_rotation_message(source_job: JobRecord, job_id: int) -> str:
    payload = JobPayload.from_json(source_job.payload_json)
    action = SupportedAction(source_job.action)
    base_message = _build_text_request_queued_message(action, job_id, payload.compression_preset)
    return f"Ripeto la stessa operazione senza rotazione automatica del PDF.\n{base_message}"


def _build_quick_action_guidance(session: UserSession | None, text: str) -> str | None:
    normalized = _normalize_free_text(text)

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

    if "foto in a4" in normalized or "immagini in a4" in normalized:
        if session is None or not session.files:
            return "Inviami una o piu immagini e ti guidero subito verso un PDF impaginato in A4."
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return "Perfetto: scegli 'PDF da immagini' e poi conferma l'impaginazione A4. Se vuoi, puoi anche aggiungere altre foto prima."
        return "Per il template 'foto in A4' devo partire da immagini o foto, non da PDF."

    if "scansiona e comprimi" in normalized or ("scansiona" in normalized and "comprimi" in normalized):
        if session is None or not session.files:
            return (
                "Inviami una o piu foto del documento. Ti conviene partire con un PDF da immagini, meglio ancora con ritaglio bordi, "
                "e poi comprimere il risultato finale con un secondo passaggio guidato."
            )
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return (
                "Per questo flusso ti conviene: 1) creare un PDF da immagini, meglio con ritaglio bordi se serve; "
                "2) comprimere il PDF finale dal messaggio risultato, senza ricaricarlo."
            )
        if {item.kind for item in session.files} == {FileKind.PDF}:
            return "Se hai gia un PDF, puoi saltare la parte scansione e comprimere direttamente il file corrente."

    return None


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
        require_new_users_or_completed_actions=True,
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
    require_new_users_or_completed_actions: bool = False,
) -> None:
    if not should_send:
        return
    meta_key = f"admin_report_{period}_last_sent"
    if deps.session_store.get_meta(meta_key) == report_date:
        return
    if not _period_has_useful_admin_data(
        deps,
        since_days=since_days,
        require_new_users_or_completed_actions=require_new_users_or_completed_actions,
    ):
        return
    report_text = _build_periodic_admin_report(deps, since_days=since_days, title=title)
    for admin_user_id in deps.settings.admin_user_ids:
        await application.bot.send_message(chat_id=admin_user_id, text=report_text)
    deps.session_store.set_meta(meta_key, report_date)


def _period_has_useful_admin_data(
    deps: BotDependencies,
    *,
    since_days: int,
    require_new_users_or_completed_actions: bool = False,
) -> bool:
    stats = deps.session_store.build_admin_stats()
    known_users_total = stats.known_users_last_24h if since_days <= 1 else stats.known_users_last_7d
    completed_actions_total = (
        stats.completed_actions_last_24h if since_days <= 1 else stats.completed_actions_last_7d
    )
    if require_new_users_or_completed_actions:
        return known_users_total > 0 or completed_actions_total > 0
    if completed_actions_total > 0:
        return True
    if deps.session_store.list_failed_actions(limit=1, since_days=since_days):
        return True
    return False


def _build_periodic_admin_report(deps: BotDependencies, *, since_days: int, title: str) -> str:
    stats = deps.session_store.build_admin_stats()
    top_users = deps.session_store.list_top_users(limit=5, since_days=since_days)
    failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=since_days)
    recent_failed_jobs = deps.session_store.list_recent_jobs(
        limit=5,
        statuses=(JobStatus.FAILED,),
        since_days=since_days,
    )
    recent_completed_jobs = deps.session_store.list_recent_jobs(
        limit=5,
        statuses=(JobStatus.SUCCEEDED,),
        since_days=since_days,
    )
    if since_days <= 1:
        activity_window_label = "ultime 24 ore"
        completed_jobs_heading = "Job completati nelle ultime 24 ore"
        failed_jobs_heading = "Job falliti nelle ultime 24 ore"
    else:
        activity_window_label = "della settimana"
        completed_jobs_heading = "Job completati della settimana"
        failed_jobs_heading = "Job falliti della settimana"
    report_body = _build_admin_report(
        stats,
        top_users,
        failed_actions,
        recent_failed_jobs,
        recent_completed_jobs,
        activity_window_label=activity_window_label,
        completed_jobs_heading=completed_jobs_heading,
        failed_jobs_heading=failed_jobs_heading,
    )
    return f"{title}\n\n{report_body}"


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
        result_message = await _send_result(
            application.bot,
            job.chat_id,
            job.reply_to_message_id,
            result,
            source_action=SupportedAction(job.action),
            source_job_id=job.id,
        )
        if result_message is not None and getattr(result_message, "document", None) is not None:
            result_document = result_message.document
            result_file_id = getattr(result_document, "file_id", None)
            result_file_name = getattr(result_document, "file_name", None)
            if isinstance(result_file_id, str) and (
                result_file_name is None or isinstance(result_file_name, str)
            ) and _infer_document_kind(result_document) == FileKind.PDF:
                deps.session_store.save(
                    _build_result_pdf_session(
                        job.user_id,
                        result_file_id,
                        result_file_name,
                    )
                )
    finally:
        deps.processor.cleanup_job_dir(job_dir)


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
    deps.session_store.set_user_preference(user_id, "image_pdf_layout", "a4" if image_pdf_use_a4 else "original")
    deps.session_store.set_user_preference(user_id, "image_pdf_margin_px", str(image_pdf_margin_px))
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
    source_action: SupportedAction | None = None,
    source_job_id: int | None = None,
    ):
    with result.output_path.open("rb") as payload:
        return await bot.send_document(
            chat_id=chat_id,
            document=payload,
            filename=result.output_name,
            caption=_build_result_delivery_message(result, source_action),
            reply_to_message_id=reply_to_message_id,
            reply_markup=_build_result_followup_keyboard(result, source_action, source_job_id),
        )


def _sum_file_sizes(paths) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total
