from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime
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
    build_main_menu_keyboard,
    build_rotation_keyboard,
)
from docmolder.messages import (
    ADMIN_ONLY_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    GENERIC_ERROR_MESSAGE,
    HELP_MESSAGE,
    MIXED_SESSION_MESSAGE,
    PROCESSING_MESSAGE,
    SESSION_EMPTY_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    WELCOME_MESSAGE,
)
from docmolder.models import CompressionPreset, FileKind, JobRecord, SupportedAction, UserSession
from docmolder.processing import DocumentProcessor, ProcessingResult, ProcessingUserError
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
    requeued_jobs = deps.session_store.requeue_incomplete_jobs()
    for job in requeued_jobs:
        await deps.job_queue.put(job.id)
    if requeued_jobs:
        logger.info("Ripresi %s job incompleti dalla coda persistente.", len(requeued_jobs))
    deps.job_worker_task = application.create_task(_job_worker(application))


async def _post_shutdown(application: Application) -> None:
    deps: BotDependencies = application.bot_data["deps"]
    if deps.job_worker_task is not None:
        deps.job_worker_task.cancel()
        try:
            await deps.job_worker_task
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
    await update.effective_message.reply_text(_build_admin_report(stats))


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
    await update.effective_message.reply_text("Sessione azzerata. Puoi inviarmi nuovi file quando vuoi.")


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

    if _exceeds_file_size_limit(document.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_build_file_too_large_message(deps.settings.max_file_size_mb))
        return

    session = _get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text("Hai raggiunto il numero massimo di file per questa sessione. Usa /reset per ricominciare.")
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

    best_photo = _pick_best_photo(photos)
    if _exceeds_file_size_limit(best_photo.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_build_file_too_large_message(deps.settings.max_file_size_mb))
        return

    session = _get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text("Hai raggiunto il numero massimo di file per questa sessione. Usa /reset per ricominciare.")
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
            "Hai scelto di ruotare le pagine. Seleziona di quanto ruotare il PDF.",
            reply_markup=build_rotation_keyboard(),
        )
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


async def handle_rotation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await query.answer()
    degrees = int((query.data or "").removeprefix("rotate:"))
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
        f"Rotazione presa in carico. Job #{job.id} in coda.\nTi invio il risultato appena è pronto."
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
    if text == "Cosa posso fare":
        await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())
        return
    if text == "Mostra sessione":
        await status_command(update, context)
        return
    if text == "Azzera sessione":
        await reset_command(update, context)
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


def _build_admin_report(stats: dict[str, int]) -> str:
    timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M")
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
        f"- Falliti: {stats['jobs_failed']}\n\n"
        "Dettaglio operazioni:\n"
        f"- PDF da immagini: {stats['images_to_pdf_total']}\n"
        f"- Comprimi PDF: {stats['pdf_compress_total']}\n"
        f"- Scala di grigi: {stats['pdf_grayscale_total']}\n"
        f"- Unisci PDF: {stats['pdf_merge_total']}\n"
        f"- Ruota PDF: {stats['pdf_rotate_total']}\n"
        f"- Correggi orientamento: {stats['auto_orient_total']}"
    )


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
    application.add_handler(CallbackQueryHandler(handle_compression_callback, pattern=r"^compress:"))
    application.add_handler(CallbackQueryHandler(handle_rotation_callback, pattern=r"^rotate:"))
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


async def _enqueue_job(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    reply_to_message_id: int | None,
    action: SupportedAction,
    session: UserSession,
    compression_preset: CompressionPreset | None = None,
    rotate_degrees: int | None = None,
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
        text=f"{PROCESSING_MESSAGE}\nJob #{job.id} in elaborazione.",
        reply_to_message_id=job.reply_to_message_id,
    )

    try:
        result = await _run_job_payload(application, job)
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

    deps.session_store.mark_job_succeeded(job.id, result.message)
    deps.session_store.record_completed_action(job.user_id, job.action)
    await _send_result(application.bot, job.chat_id, job.reply_to_message_id, result)


async def _run_job_payload(
    application: Application,
    job: JobRecord,
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

    job_dir = deps.processor.create_job_dir(session.user_id)
    try:
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
        )
        return result
    finally:
        deps.processor.cleanup_job_dir(job_dir)


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


async def _send_result(bot, chat_id: int, reply_to_message_id: int | None, result: ProcessingResult) -> None:
    with result.output_path.open("rb") as payload:
        await bot.send_document(
            chat_id=chat_id,
            document=payload,
            filename=result.output_name,
            caption=result.message,
            reply_to_message_id=reply_to_message_id,
        )
