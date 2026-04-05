from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Document, InlineKeyboardMarkup, PhotoSize, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from docmolder.config import Settings
from docmolder.keyboards import build_actions_keyboard, build_compression_keyboard, build_rotation_keyboard
from docmolder.messages import (
    GENERIC_ERROR_MESSAGE,
    PROCESSING_MESSAGE,
    SESSION_EMPTY_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    WELCOME_MESSAGE,
)
from docmolder.models import CompressionPreset, FileKind, SupportedAction, UserSession
from docmolder.processing import DocumentProcessor, ProcessingResult
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


def _is_authorized(user_id: int | None, settings: Settings) -> bool:
    if user_id is None:
        return False
    if not settings.allowed_user_ids:
        return True
    return user_id in settings.allowed_user_ids


def _get_dependencies(context: ContextTypes.DEFAULT_TYPE) -> BotDependencies:
    return context.application.bot_data["deps"]


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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return

    await update.effective_message.reply_text(WELCOME_MESSAGE)


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return

    _cancel_pending_image_notification(user.id, deps)
    deps.session_store.delete(user.id)
    await update.effective_message.reply_text("Sessione azzerata. Puoi inviarmi nuovi file quando vuoi.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    if not _is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await update.effective_message.reply_text(SESSION_EMPTY_MESSAGE)
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

    document = message.document
    if document is None:
        return

    kind = _infer_document_kind(document)
    if kind is None:
        await message.reply_text("Per ora supporto solo PDF e immagini.")
        return

    session = _get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text("Hai raggiunto il numero massimo di file per questa sessione. Usa /reset per ricominciare.")
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

    photos = message.photo
    if not photos:
        return

    session = _get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text("Hai raggiunto il numero massimo di file per questa sessione. Usa /reset per ricominciare.")
        return

    best_photo = _pick_best_photo(photos)
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
            "Hai scelto di ruotare le pagine. Seleziona di quanto ruotare il PDF.",
            reply_markup=build_rotation_keyboard(),
        )
        return

    try:
        result = await _run_action(
            update=update,
            context=context,
            action=SupportedAction(action),
            session=session,
        )
    except Exception:
        logger.exception("Errore durante l'azione %s", action)
        await query.edit_message_text(GENERIC_ERROR_MESSAGE)
        return

    deps.session_store.delete(user.id)
    await query.edit_message_text(result.message)


async def handle_compression_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()
    preset = (query.data or "").removeprefix("compress:")
    user = query.from_user
    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    try:
        result = await _run_action(
            update=update,
            context=context,
            action=SupportedAction.PDF_COMPRESS,
            session=session,
            compression_preset=CompressionPreset(preset),
        )
    except Exception:
        logger.exception("Errore durante la compressione")
        await query.edit_message_text(GENERIC_ERROR_MESSAGE)
        return

    deps.session_store.delete(user.id)
    await query.edit_message_text(result.message)


async def handle_rotation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()
    degrees = int((query.data or "").removeprefix("rotate:"))
    user = query.from_user
    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    try:
        result = await _run_action(
            update=update,
            context=context,
            action=SupportedAction.PDF_ROTATE,
            session=session,
            rotate_degrees=degrees,
        )
    except Exception:
        logger.exception("Errore durante la rotazione PDF")
        await query.edit_message_text(GENERIC_ERROR_MESSAGE)
        return

    deps.session_store.delete(user.id)
    await query.edit_message_text(result.message)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Errore non gestito", exc_info=context.error)


def build_application(settings: Settings) -> Application:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        level=logging.INFO,
    )

    session_store = SQLiteSessionStore(settings.database_path)
    processor = DocumentProcessor(runtime_dir=settings.runtime_dir)
    deps = BotDependencies(settings=settings, session_store=session_store, processor=processor)

    application = Application.builder().token(settings.telegram_token).build()
    application.bot_data["deps"] = deps

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(handle_compression_callback, pattern=r"^compress:"))
    application.add_handler(CallbackQueryHandler(handle_rotation_callback, pattern=r"^rotate:"))
    application.add_handler(CallbackQueryHandler(handle_action_callback, pattern=r"^action:"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
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
            "Puoi inviarmi altre immagini per creare un PDF unico in formato A4 con margini, "
            "oppure scegliere subito un'azione."
        )

    return (
        f"Ho ricevuto {image_count} immagini nella stessa sessione.\n"
        "Puoi creare un PDF unico in formato A4 con margini oppure correggere l'orientamento."
    )


async def _run_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    action: SupportedAction,
    session: UserSession,
    compression_preset: CompressionPreset | None = None,
    rotate_degrees: int | None = None,
) -> ProcessingResult:
    deps = _get_dependencies(context)
    message = update.effective_message or update.callback_query.message
    if action not in infer_supported_actions(session):
        raise ValueError(f"Azione non valida per la sessione corrente: {action}")
    await message.reply_text(PROCESSING_MESSAGE)

    job_dir = deps.processor.create_job_dir(session.user_id)
    try:
        input_dir = job_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        downloaded_paths = await _download_session_files(context, session, input_dir)

        result = await asyncio.to_thread(
            deps.processor.process,
            action,
            downloaded_paths,
            build_output_stem(action),
            compression_preset,
            rotate_degrees,
        )

        await _send_result(message, result)
        return result
    finally:
        deps.processor.cleanup_job_dir(job_dir)


async def _download_session_files(
    context: ContextTypes.DEFAULT_TYPE,
    session: UserSession,
    input_dir: Path,
) -> list[Path]:
    downloaded_paths: list[Path] = []
    for index, session_file in enumerate(session.files, start=1):
        telegram_file = await context.bot.get_file(session_file.telegram_file_id)
        file_name = sanitize_filename(session_file.file_name)
        target_path = input_dir / f"{index:02d}_{file_name}"
        await telegram_file.download_to_drive(custom_path=str(target_path))
        downloaded_paths.append(target_path)
    return downloaded_paths


async def _send_result(message, result: ProcessingResult) -> None:
    with result.output_path.open("rb") as payload:
        await message.reply_document(
            document=payload,
            filename=result.output_name,
            caption=result.message,
        )
