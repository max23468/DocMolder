from __future__ import annotations

import asyncio
import html
import logging
import re
import shutil
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import TypedDict
from zoneinfo import ZoneInfo

from telegram import Document, InlineKeyboardMarkup, Message, PhotoSize, Update, User
from telegram import MenuButtonCommands
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from docmolder.config import Settings
from docmolder.branding import (
    LEGACY_MENU_LABELS,
    TELEGRAM_DESCRIPTION,
    TELEGRAM_NAME,
    TELEGRAM_SHORT_DESCRIPTION,
    build_telegram_commands,
)
from docmolder.keyboards import (
    build_actions_keyboard,
    build_access_review_keyboard,
    build_admin_dashboard_keyboard,
    build_compression_keyboard,
    build_history_keyboard,
    build_images_pdf_layout_keyboard,
    build_images_pdf_margin_keyboard,
    build_main_menu_keyboard,
    build_rotate_keyboard,
    build_result_pdf_keyboard,
    build_split_output_keyboard,
)
from docmolder.job_flow import (
    enqueue_job as enqueue_job_flow,
    enqueue_job_from_existing_payload as enqueue_job_from_existing_payload_flow,
    run_job_payload as run_job_payload_flow,
)
from docmolder.healthcheck import build_health_report
from docmolder.logging_utils import log_event
from docmolder.messages import (
    ADMIN_ONLY_MESSAGE,
    FILE_TOO_LARGE_MESSAGE,
    GENERIC_ERROR_MESSAGE,
    HELP_MESSAGE,
    JOB_QUEUE_LIMIT_MESSAGE,
    MIXED_SESSION_MESSAGE,
    SERVICE_UNAVAILABLE_MESSAGE,
    SESSION_EMPTY_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    UPLOAD_RATE_LIMIT_MESSAGE,
    WELCOME_MESSAGE,
    build_pending_action_prompt,
    build_pending_action_queued_message,
    build_processing_started_message,
    build_text_request_queued_message,
)
from docmolder.models import (
    AdminActionStat,
    AdminStats,
    AdminUserStat,
    CompressionPreset,
    FileKind,
    JobPayload,
    JobRecord,
    JobStatus,
    PendingActionValue,
    SupportedAction,
    UserSession,
)
from docmolder.processing import (
    A4_MARGIN_NARROW_PX,
    A4_MARGIN_NONE_PX,
    A4_MARGIN_WIDE_PX,
    DocumentProcessor,
    ProcessingResult,
    ProcessingUserError,
)
from docmolder.retry import run_async_with_retry
from docmolder.action_catalog import (
    build_session_file,
    build_session_recap,
    get_action_label,
    infer_exposed_actions,
    infer_result_followup_actions,
    infer_supported_actions,
    sanitize_filename,
)
from docmolder.session_store import SQLiteSessionStore, SessionStore
from docmolder.telegram_messaging import send_telegram_message
from docmolder.text_requests import (
    _build_quick_action_guidance,
    _extract_rotation_degrees,
    _infer_split_output_zip,
    _normalize_keyword_text,
    _normalize_page_selection_text,
    _parse_image_pdf_layout_choice,
    _parse_image_pdf_margin_choice,
    _resolve_text_request,
    _tokenize_keyword_text,
    _validate_page_input_text,
)

logger = logging.getLogger(__name__)

_TELEGRAM_TOKEN_IN_URL_RE = re.compile(r"/bot[^/]+/")

_build_pending_action_prompt = build_pending_action_prompt
_build_pending_action_queued_message = build_pending_action_queued_message
_build_processing_started_message = build_processing_started_message
_build_text_request_queued_message = build_text_request_queued_message

_PENDING_IMAGES_PDF_LAYOUT_PREFIX = "images_pdf_layout"
_PENDING_IMAGES_PDF_MARGIN_PREFIX = "images_pdf_margin"
_SERVICE_MODE_META_KEY = "service_mode"
_SERVICE_MODE_NORMAL = "normal"
_SERVICE_MODE_MAINTENANCE = "maintenance"
_ACCESS_META_PREFIX = "access:"
_ACCESS_STATUS_PENDING = "pending"
_ACCESS_STATUS_APPROVED = "approved"
_ACCESS_STATUS_BLOCKED = "blocked"
_ACCESS_STATUS_REJECTED = "rejected"
_TELEGRAM_RETRY_ATTEMPTS = 3
_TELEGRAM_METRIC_PREFIX = "telegram_metric:"
_ADMIN_CALLBACK_REPLAY_WINDOW_SECONDS = 5
_NEW_USER_NOTIFICATION_COOLDOWN_SECONDS = 120
_BRANDING_SYNC_RETRY_AT_META_KEY = "branding_sync:retry_at"
_BRANDING_SYNC_DEFAULT_BACKOFF_SECONDS = 3600


class PendingActionEnqueueKwargs(TypedDict, total=False):
    page_selection: str
    watermark_text: str
    split_output_zip: bool




class AdminAlertPayload(TypedDict):
    key: str
    signature: str
    text: str


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


def _access_meta_key(user_id: int) -> str:
    return f"{_ACCESS_META_PREFIX}{user_id}:status"


def _get_dynamic_access_status(deps: BotDependencies, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    value = deps.session_store.get_meta(_access_meta_key(user_id))
    return value.strip().lower() if value else None


def _set_dynamic_access_status(deps: BotDependencies, user_id: int, status: str) -> None:
    deps.session_store.set_meta(_access_meta_key(user_id), status)


def _is_authorized_for_deps(user_id: int | None, deps: BotDependencies) -> bool:
    if user_id is None:
        return False
    if _is_admin(user_id, deps.settings):
        return True
    dynamic_status = _get_dynamic_access_status(deps, user_id)
    if dynamic_status in {_ACCESS_STATUS_BLOCKED, _ACCESS_STATUS_REJECTED}:
        return False
    if dynamic_status == _ACCESS_STATUS_APPROVED:
        return True
    return _is_authorized(user_id, deps.settings)


def _list_dynamic_access_statuses(deps: BotDependencies) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for key, value in deps.session_store.list_meta(_ACCESS_META_PREFIX).items():
        suffix = key.removeprefix(_ACCESS_META_PREFIX)
        raw_user_id = suffix.split(":", 1)[0]
        try:
            user_id = int(raw_user_id)
        except ValueError:
            continue
        entries.append((user_id, value))
    return sorted(entries, key=lambda item: item[0])


def _is_admin(user_id: int | None, settings: Settings) -> bool:
    if user_id is None:
        return False
    return user_id in settings.admin_user_ids


def _get_dependencies(context: ContextTypes.DEFAULT_TYPE) -> BotDependencies:
    return context.application.bot_data["deps"]


def _get_service_mode(deps: BotDependencies) -> str:
    service_mode = deps.session_store.get_meta(_SERVICE_MODE_META_KEY)
    if service_mode in {_SERVICE_MODE_NORMAL, _SERVICE_MODE_MAINTENANCE}:
        return service_mode
    return _SERVICE_MODE_NORMAL


def _set_service_mode(deps: BotDependencies, service_mode: str) -> None:
    deps.session_store.set_meta(_SERVICE_MODE_META_KEY, service_mode)


def _is_service_paused(deps: BotDependencies) -> bool:
    return _get_service_mode(deps) == _SERVICE_MODE_MAINTENANCE


def _build_service_status_label(deps: BotDependencies) -> str:
    return "manutenzione" if _is_service_paused(deps) else "attivo"


def _build_service_unavailable_message() -> str:
    return SERVICE_UNAVAILABLE_MESSAGE


def _increment_meta_counter(deps: BotDependencies, key: str, amount: int = 1) -> None:
    current_value = deps.session_store.get_meta(key)
    try:
        parsed_value = int(current_value) if current_value is not None else 0
    except ValueError:
        parsed_value = 0
    deps.session_store.set_meta(key, str(parsed_value + amount))


def _get_meta_counter(deps: BotDependencies, key: str) -> int:
    current_value = deps.session_store.get_meta(key)
    try:
        return int(current_value) if current_value is not None else 0
    except ValueError:
        return 0


def _record_command_metric(deps: BotDependencies, command_name: str) -> None:
    _increment_meta_counter(deps, f"{_TELEGRAM_METRIC_PREFIX}command:{command_name}")


def _record_callback_metric(deps: BotDependencies, callback_name: str) -> None:
    _increment_meta_counter(deps, f"{_TELEGRAM_METRIC_PREFIX}callback:{callback_name}")


def _record_upload_metric(deps: BotDependencies, upload_kind: str) -> None:
    _increment_meta_counter(deps, f"{_TELEGRAM_METRIC_PREFIX}upload:{upload_kind}")


def _append_audit_log(
    deps: BotDependencies,
    event_type: str,
    *,
    actor_user_id: int | None,
    outcome: str,
    target_user_id: int | None = None,
    detail: str = "",
) -> None:
    try:
        deps.session_store.append_audit_log_entry(
            event_type,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            outcome=outcome,
            detail=detail,
        )
    except Exception:
        logger.exception("Impossibile registrare audit log %s.", event_type)


def _callback_replay_meta_key(user_id: int, callback_data: str, message_id: int | None) -> str:
    return f"callback_replay:{user_id}:{message_id or 0}:{callback_data}"


def _is_replayed_callback(deps: BotDependencies, *, user_id: int, callback_data: str, message_id: int | None) -> bool:
    meta_key = _callback_replay_meta_key(user_id, callback_data, message_id)
    last_seen_raw = deps.session_store.get_meta(meta_key)
    now = datetime.now(timezone.utc)
    last_seen = _parse_meta_datetime(last_seen_raw)
    deps.session_store.set_meta(meta_key, now.isoformat())
    if last_seen is None:
        return False
    return (now - last_seen).total_seconds() < _ADMIN_CALLBACK_REPLAY_WINDOW_SECONDS


def _invalid_callback_message() -> str:
    return "Richiesta non valida o scaduta. Riprova dal messaggio più recente."


def _new_user_admin_meta_key(admin_user_id: int, suffix: str) -> str:
    return f"new_user_notice:{admin_user_id}:{suffix}"


async def _telegram_api_call(label: str, call, *args, **kwargs):
    deps = kwargs.pop("_deps", None)

    async def action():
        return await call(*args, **kwargs)

    def should_retry(exc: Exception) -> bool:
        return isinstance(exc, (RetryAfter, TimedOut, NetworkError))

    def delay_for_exception(exc: Exception, attempt_index: int) -> float | None:
        if isinstance(exc, RetryAfter):
            return float(max(1, int(getattr(exc, "retry_after", 1))))
        return float(attempt_index + 1)

    def on_retry(exc: Exception, attempt_no: int, total_attempts: int, delay: float) -> None:
        if isinstance(exc, RetryAfter):
            logger.warning("Telegram rate limit su %s, ritento tra %ss", label, int(delay))
            if isinstance(deps, BotDependencies):
                _increment_meta_counter(deps, f"{_TELEGRAM_METRIC_PREFIX}retry_after:{label}")
        else:
            logger.warning(
                "Errore temporaneo Telegram su %s (%s), ritento tra %ss",
                label,
                type(exc).__name__,
                int(delay),
            )
            if isinstance(deps, BotDependencies):
                _increment_meta_counter(deps, f"{_TELEGRAM_METRIC_PREFIX}network_retry:{label}")
        log_event(
            logger,
            logging.WARNING,
            "telegram_api_retry",
            label=label,
            error_type=type(exc).__name__,
            attempt=attempt_no,
            total_attempts=total_attempts,
            delay_seconds=round(delay, 2),
        )

    return await run_async_with_retry(
        action,
        max_attempts=_TELEGRAM_RETRY_ATTEMPTS,
        should_retry=should_retry,
        on_retry=on_retry,
        delay_for_exception=delay_for_exception,
        jitter_max=0,
        sleep_fn=asyncio.sleep,
    )


async def _safe_answer_callback(query) -> None:
    try:
        await _telegram_api_call("answerCallbackQuery", query.answer)
    except TelegramError:
        logger.debug("Impossibile rispondere alla callback Telegram.", exc_info=True)


async def _safe_send_message(
    bot,
    *,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    deps: BotDependencies | None = None,
    **kwargs,
):
    parse_mode = kwargs.pop("parse_mode", None)

    async def api_call(label: str, call, **call_kwargs):
        return await _telegram_api_call(label, call, _deps=deps, **call_kwargs)

    return await send_telegram_message(
        bot,
        chat_id=chat_id,
        text=text,
        api_call=api_call,
        reply_to_message_id=reply_to_message_id,
        parse_mode=parse_mode,
        **kwargs,
    )


def _runtime_disk_snapshot(path: Path) -> tuple[int, int, int] | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return usage.total, usage.used, usage.free


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
    split_output_zip: bool = True,
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
        split_output_zip=split_output_zip,
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
    await _sync_telegram_branding(application, deps.settings, deps.session_store)
    requeued_jobs = deps.session_store.requeue_incomplete_jobs()
    for job in requeued_jobs:
        await deps.job_queue.put(job.id)
    if requeued_jobs:
        logger.info("Ripresi %s job incompleti dalla coda persistente.", len(requeued_jobs))
        log_event(logger, logging.INFO, "jobs_requeued_on_startup", count=len(requeued_jobs))
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


async def _sync_telegram_branding(
    application: Application,
    settings: Settings,
    session_store: SessionStore | None = None,
) -> None:
    if not settings.telegram_brand_sync_enabled:
        return

    retry_at = _parse_meta_datetime(session_store.get_meta(_BRANDING_SYNC_RETRY_AT_META_KEY)) if session_store else None
    now = datetime.now(timezone.utc)
    if retry_at is not None and now < retry_at:
        log_event(
            logger,
            logging.INFO,
            "telegram_branding_sync_skipped",
            reason="backoff_active",
            retry_at=retry_at.isoformat(),
        )
        return

    bot = application.bot
    language_codes = tuple(dict.fromkeys(("", settings.default_language.strip())))
    commands = build_telegram_commands()

    try:
        for language_code in language_codes:
            kwargs = {"language_code": language_code} if language_code else {}
            await bot.set_my_name(TELEGRAM_NAME, **kwargs)
            await bot.set_my_description(TELEGRAM_DESCRIPTION, **kwargs)
            await bot.set_my_short_description(TELEGRAM_SHORT_DESCRIPTION, **kwargs)
            await bot.set_my_commands(commands, **kwargs)
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        if session_store is not None:
            session_store.set_meta(_BRANDING_SYNC_RETRY_AT_META_KEY, "")
        log_event(logger, logging.INFO, "telegram_branding_sync_completed")
    except RetryAfter as exc:
        retry_after = max(1, int(getattr(exc, "retry_after", _BRANDING_SYNC_DEFAULT_BACKOFF_SECONDS)))
        retry_at = now + timedelta(seconds=retry_after)
        if session_store is not None:
            session_store.set_meta(_BRANDING_SYNC_RETRY_AT_META_KEY, retry_at.isoformat())
        log_event(
            logger,
            logging.WARNING,
            "telegram_branding_sync_rate_limited",
            retry_after_seconds=retry_after,
            retry_at=retry_at.isoformat(),
        )
    except TelegramError:
        logger.warning("Non sono riuscito a sincronizzare il branding Telegram del bot.", exc_info=True)


def _has_capacity_for_new_job(user_id: int, deps: BotDependencies) -> bool:
    return deps.session_store.count_active_jobs_for_user(user_id) < deps.settings.max_active_jobs_per_user


def _is_latest_job_rerun_text(text: str) -> bool:
    keyword_text = _normalize_keyword_text(text)
    if not keyword_text:
        return False
    padded_text = f" {keyword_text} "
    rerun_fragments = (
        " ripeti ",
        " ripetere ",
        " ripetilo ",
        " rilancia ",
        " rilanciare ",
        " rilancialo ",
        " rifai ",
        " rifare ",
        " rifallo ",
        " riesegui ",
        " rieseguire ",
        " rieseguilo ",
    )
    contextual_fragments = (
        " ultimo ",
        " ultimo job ",
        " ultimo lavoro ",
        " ultimo flusso ",
        " quello ",
        " precedente ",
    )
    return any(fragment in padded_text for fragment in rerun_fragments) and any(
        fragment in padded_text for fragment in contextual_fragments
    )


def _mentions_context_reference(text: str) -> bool:
    keyword_text = _normalize_keyword_text(text)
    if not keyword_text:
        return False
    padded_text = f" {keyword_text} "
    context_fragments = (
        " questo pdf ",
        " quel pdf ",
        " quello ",
        " questo documento ",
        " quel documento ",
        " ultimo pdf ",
        " ultimo file ",
        " ultimo documento ",
        " ultimo job ",
        " file precedente ",
        " documento precedente ",
        " comprimilo ",
        " alleggeriscilo ",
        " riducilo ",
        " dividilo ",
        " separalo ",
        " giralo ",
        " ruotalo ",
        " rifallo ",
    )
    return any(fragment in padded_text for fragment in context_fragments)


def _build_missing_context_reference_message(deps: BotDependencies, user_id: int) -> str:
    latest_jobs = deps.session_store.list_user_jobs(user_id, limit=1)
    if latest_jobs:
        return (
            "Ho capito il riferimento, ma non ho una sessione attiva con un PDF sicuro su cui lavorare.\n"
            "Se vuoi ripetere l'ultimo job, scrivi /last. Se invece vuoi modificare un PDF preciso, reinviamelo e riparto da quello."
        )
    return (
        "Ho capito il riferimento, ma non ho ancora un PDF attivo in questa chat.\n"
        "Inviami il file e poi puoi scrivere frasi come `comprimi questo PDF` o `dividilo senza zip`."
    )


def _filter_keyboard_for_session(session: UserSession) -> InlineKeyboardMarkup | None:
    return build_actions_keyboard(infer_exposed_actions(session))


def _is_image_pdf_action(action: SupportedAction) -> bool:
    return action in {
        SupportedAction.IMAGES_TO_PDF,
        SupportedAction.IMAGES_TO_PDF_CROP,
        SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
        SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
    }


async def _prepare_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    require_admin: bool = False,
) -> tuple[BotDependencies, User, Message] | None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)

    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return None

    is_allowed = _is_admin(user.id, deps.settings) if require_admin else _is_authorized_for_deps(user.id, deps)
    if not is_allowed:
        await message.reply_text(ADMIN_ONLY_MESSAGE if require_admin else UNAUTHORIZED_MESSAGE)
        return None

    if not require_admin and _is_service_paused(deps) and not _is_admin(user.id, deps.settings):
        await message.reply_text(_build_service_unavailable_message())
        return None

    await _maybe_notify_admins_about_new_user(user, context)
    return deps, user, message


def _validate_session_for_upload(session: UserSession, kind: FileKind, max_session_files: int) -> str | None:
    if len(session.files) >= max_session_files:
        return _build_session_file_limit_message(max_session_files)
    if session.files and any(item.kind != kind for item in session.files):
        return MIXED_SESSION_MESSAGE
    return None


def _save_uploaded_file(session: UserSession, session_file, deps: BotDependencies) -> None:
    session.files.append(session_file)
    session.pending_action = None
    session.touch()
    deps.session_store.save(session)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "start")

    deep_link_payload = (context.args[0].strip() if getattr(context, "args", None) else "").lower()
    if deep_link_payload:
        handled = await _handle_start_payload(deep_link_payload, deps, user.id, message, context)
        if handled:
            return

    await message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=build_main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, _user, message = prepared
    _record_command_metric(deps, "help")

    await message.reply_text(
        HELP_MESSAGE,
        reply_markup=build_main_menu_keyboard(),
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "history")

    jobs = deps.session_store.list_user_jobs(user.id, limit=5)
    if not jobs:
        await message.reply_text(
            "Non hai ancora uno storico lavori. Inviami immagini o PDF e terrò traccia degli ultimi job qui.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    await message.reply_text(
        _build_user_history_summary(jobs),
        reply_markup=build_history_keyboard([job.id for job in jobs]),
    )


async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "last")

    await _rerun_latest_user_job(
        context=context,
        deps=deps,
        user_id=user.id,
        message=message,
    )


async def _rerun_latest_user_job(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    deps: BotDependencies,
    user_id: int,
    message: Message,
) -> None:
    jobs = deps.session_store.list_user_jobs(user_id, limit=1)
    if not jobs:
        await message.reply_text(
            "Non ho ancora un job da rilanciare per te. Inviami immagini o PDF e poi potrò ripetere l'ultimo flusso.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    if not _has_capacity_for_new_job(user_id, deps):
        await message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return

    source_job = jobs[0]
    rerun_job = await _enqueue_job_from_existing_payload(
        context=context,
        source_job=source_job,
        reply_to_message_id=message.message_id,
    )
    await message.reply_text(_build_history_rerun_message(source_job, rerun_job.id))


async def access_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "access")
    await message.reply_text(_build_access_status_message(deps, user.id), reply_markup=build_main_menu_keyboard())


async def policy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    deps.session_store.register_user(user.id, user.username, user.first_name, user.last_name)
    _record_command_metric(deps, "policy")
    await message.reply_text(_build_policy_message(deps), reply_markup=build_main_menu_keyboard())


async def request_access_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    deps.session_store.register_user(user.id, user.username, user.first_name, user.last_name)
    _record_command_metric(deps, "request_access")

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

    _set_dynamic_access_status(deps, user.id, _ACCESS_STATUS_PENDING)
    _append_audit_log(deps, "request_access", actor_user_id=user.id, outcome="pending", target_user_id=user.id)
    await _notify_admins_about_access_request(user, context, deps)
    await message.reply_text(
        "Richiesta accesso inviata all'admin. Ti basta attendere: quando viene approvata potrai usare il bot.",
        reply_markup=build_main_menu_keyboard(),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    _record_command_metric(deps, "admin")

    stats = deps.session_store.build_admin_stats()
    top_users = deps.session_store.list_top_users(limit=5, since_days=7)
    failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=7)
    recent_failed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
    recent_completed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))
    await message.reply_text(
        _build_admin_report(stats, top_users, failed_actions, recent_failed_jobs, recent_completed_jobs),
        reply_markup=build_admin_dashboard_keyboard(service_paused=_is_service_paused(deps)),
    )


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    _record_command_metric(deps, "queue")
    await message.reply_text(
        _build_admin_queue_report(deps),
        reply_markup=build_admin_dashboard_keyboard(service_paused=_is_service_paused(deps)),
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    _record_command_metric(deps, "health")
    await message.reply_text(
        _build_admin_health_report(deps),
        reply_markup=build_admin_dashboard_keyboard(service_paused=_is_service_paused(deps)),
    )


async def maintenance_overview_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    _record_command_metric(deps, "maintenance_overview")
    await message.reply_text(
        _build_admin_maintenance_overview(deps),
        reply_markup=build_admin_dashboard_keyboard(service_paused=_is_service_paused(deps)),
    )


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "pause")
    _set_service_mode(deps, _SERVICE_MODE_MAINTENANCE)
    _append_audit_log(deps, "service_mode", actor_user_id=user.id, outcome="maintenance", detail="command:/pause")
    log_event(logger, logging.INFO, "admin_service_mode_changed", actor_user_id=user.id, service_mode="maintenance")
    await message.reply_text(
        "Servizio messo in modalità manutenzione. I nuovi comandi utente vengono bloccati finché non riattivi il servizio.",
        reply_markup=build_admin_dashboard_keyboard(service_paused=True),
    )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "resume")
    _set_service_mode(deps, _SERVICE_MODE_NORMAL)
    _append_audit_log(deps, "service_mode", actor_user_id=user.id, outcome="normal", detail="command:/resume")
    log_event(logger, logging.INFO, "admin_service_mode_changed", actor_user_id=user.id, service_mode="normal")
    await message.reply_text(
        "Servizio riattivato. Il bot accetta di nuovo richieste utente normali.",
        reply_markup=build_admin_dashboard_keyboard(service_paused=False),
    )


async def metrics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    _record_command_metric(deps, "metrics")
    await message.reply_text(
        _build_telegram_metrics_report(deps),
        reply_markup=build_admin_dashboard_keyboard(service_paused=_is_service_paused(deps)),
    )


async def job_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, _user, message = prepared
    _record_command_metric(deps, "job")
    raw_selector = context.args[0].strip().lower() if getattr(context, "args", None) else ""
    job = _resolve_job_selector(deps, raw_selector)
    if job is None:
        await message.reply_text(
            "Usa `/job <id>`, `/job latest`, `/job failed`, `/job running`, `/job queued` oppure `/job succeeded`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    await message.reply_text(_build_user_history_job_detail(job))


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "retry")
    raw_args = [str(arg).strip().lower() for arg in getattr(context, "args", []) if str(arg).strip()]
    if not raw_args:
        await message.reply_text(
            "Usa `/retry <id>` oppure `/retry latest|failed|running|queued|succeeded` per rilanciare un job esistente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    selector = raw_args[0]
    disable_auto_rotate = "--no-auto-rotate" in raw_args[1:] or "no-auto-rotate" in raw_args[1:]
    source_job = _resolve_job_selector(deps, selector)
    if source_job is None:
        await message.reply_text(
            "Non trovo il job richiesto da rilanciare. Puoi usare un id oppure `latest`, `failed`, `running`, `queued`, `succeeded`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if not _has_capacity_for_new_job(source_job.user_id, deps):
        await message.reply_text(
            f"L'utente {source_job.user_id} ha già raggiunto il limite di job attivi. Riprova più tardi."
        )
        return

    rerun_job = await _enqueue_job_from_existing_payload(
        context=context,
        source_job=source_job,
        reply_to_message_id=message.message_id,
        auto_rotate_pdf=False if disable_auto_rotate else None,
    )
    _append_audit_log(
        deps,
        "admin_retry_job",
        actor_user_id=user.id,
        target_user_id=source_job.user_id,
        outcome="queued",
        detail=f"source_job_id={source_job.id} rerun_job_id={rerun_job.id} no_auto_rotate={disable_auto_rotate}",
    )
    log_event(
        logger,
        logging.INFO,
        "admin_job_retry_queued",
        actor_user_id=user.id,
        source_job_id=source_job.id,
        rerun_job_id=rerun_job.id,
        target_user_id=source_job.user_id,
        no_auto_rotate=disable_auto_rotate,
    )
    if disable_auto_rotate:
        await message.reply_text(_build_rerun_without_rotation_message(source_job, rerun_job.id))
        return
    await message.reply_text(_build_history_rerun_message(source_job, rerun_job.id))


async def access_review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context, require_admin=True)
    if prepared is None:
        return
    deps, user, message = prepared
    command = (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()
    _record_command_metric(deps, command.removeprefix("/"))
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
    _append_audit_log(
        deps,
        "access_review",
        actor_user_id=user.id,
        target_user_id=target_user_id,
        outcome=outcome,
        detail=f"command:{command}",
    )
    log_event(
        logger,
        logging.INFO,
        "access_review_completed",
        actor_user_id=user.id,
        target_user_id=target_user_id,
        outcome=outcome,
    )
    await message.reply_text(f"Stato accesso utente {target_user_id}: {outcome}.")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await _safe_answer_callback(query)

    user = query.from_user
    if not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(ADMIN_ONLY_MESSAGE)
        return
    if user is None:
        await query.edit_message_text(_invalid_callback_message())
        return
    if _is_replayed_callback(
        deps,
        user_id=user.id,
        callback_data=query.data or "",
        message_id=getattr(query.message, "message_id", None),
    ):
        await query.edit_message_text("Azione già ricevuta poco fa. Usa Aggiorna se vuoi vedere lo stato più recente.")
        return

    action = (query.data or "").removeprefix("admin:")
    _record_callback_metric(deps, f"admin:{action or 'overview'}")
    if action == "pause":
        _set_service_mode(deps, _SERVICE_MODE_MAINTENANCE)
        _append_audit_log(deps, "service_mode", actor_user_id=user.id, outcome="maintenance", detail="callback:admin:pause")
        log_event(logger, logging.INFO, "admin_service_mode_changed", actor_user_id=user.id, service_mode="maintenance")
        body = (
            "Console admin DocMolder\n"
            "Servizio impostato in modalità manutenzione.\n\n"
            f"{_build_admin_queue_report(deps)}"
        )
    elif action == "resume":
        _set_service_mode(deps, _SERVICE_MODE_NORMAL)
        _append_audit_log(deps, "service_mode", actor_user_id=user.id, outcome="normal", detail="callback:admin:resume")
        log_event(logger, logging.INFO, "admin_service_mode_changed", actor_user_id=user.id, service_mode="normal")
        body = (
            "Console admin DocMolder\n"
            "Servizio riattivato.\n\n"
            f"{_build_admin_queue_report(deps)}"
        )
    elif action == "queue":
        body = _build_admin_queue_report(deps)
    elif action == "health":
        body = _build_admin_health_report(deps)
    elif action == "metrics":
        body = _build_telegram_metrics_report(deps)
    elif action == "maintenance":
        body = _build_admin_maintenance_overview(deps)
    elif action == "failed":
        failed_job = _resolve_job_selector(deps, "failed")
        body = _build_user_history_job_detail(failed_job) if failed_job is not None else "Non vedo job falliti recenti."
    elif action == "running":
        running_job = _resolve_job_selector(deps, "running")
        body = _build_user_history_job_detail(running_job) if running_job is not None else "Non vedo job in esecuzione."
    elif action == "queued":
        queued_job = _resolve_job_selector(deps, "queued")
        body = _build_user_history_job_detail(queued_job) if queued_job is not None else "Non vedo job in coda."
    elif action == "succeeded":
        succeeded_job = _resolve_job_selector(deps, "succeeded")
        body = _build_user_history_job_detail(succeeded_job) if succeeded_job is not None else "Non vedo job riusciti recenti."
    elif action == "latest":
        latest_job = _resolve_job_selector(deps, "latest")
        body = _build_user_history_job_detail(latest_job) if latest_job is not None else "Non vedo job recenti."
    else:
        stats = deps.session_store.build_admin_stats()
        top_users = deps.session_store.list_top_users(limit=5, since_days=7)
        failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=7)
        recent_failed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
        recent_completed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))
        body = _build_admin_report(stats, top_users, failed_actions, recent_failed_jobs, recent_completed_jobs)

    try:
        await query.edit_message_text(
            body,
            reply_markup=build_admin_dashboard_keyboard(service_paused=_is_service_paused(deps)),
        )
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        raise


async def handle_access_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    query = update.callback_query
    await _safe_answer_callback(query)
    user = query.from_user
    if user is None or not _is_admin(user.id, deps.settings):
        await query.edit_message_text(ADMIN_ONLY_MESSAGE)
        return
    try:
        _, action, raw_user_id = (query.data or "").split(":", 2)
        target_user_id = int(raw_user_id)
    except (TypeError, ValueError):
        await query.edit_message_text(_invalid_callback_message())
        return
    if action == "approve":
        status = _ACCESS_STATUS_APPROVED
        outcome = "approved"
    elif action == "reject":
        status = _ACCESS_STATUS_REJECTED
        outcome = "rejected"
    else:
        await query.edit_message_text(_invalid_callback_message())
        return
    _set_dynamic_access_status(deps, target_user_id, status)
    _append_audit_log(
        deps,
        "access_review",
        actor_user_id=user.id,
        target_user_id=target_user_id,
        outcome=outcome,
        detail=f"callback:access:{action}",
    )
    await query.edit_message_text(f"Richiesta accesso utente {target_user_id}: {outcome}.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "reset")

    _cancel_pending_image_notification(user.id, deps)
    deps.session_store.delete(user.id)
    deps.session_store.clear_user_preferences(user.id)
    await message.reply_text(
        "Sessione azzerata. Ho dimenticato anche le ultime scelte rapide salvate. Puoi inviarmi nuovi file quando vuoi.",
        reply_markup=build_main_menu_keyboard(),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_command_metric(deps, "status")

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await message.reply_text(
            SESSION_EMPTY_MESSAGE,
            reply_markup=build_main_menu_keyboard(),
        )
        return

    extra_note = f"\nSto aspettando il tuo input per {_action_label(session.pending_action)}." if session.pending_action else ""
    await message.reply_text(
        f"{build_session_recap(session)}{extra_note}",
        reply_markup=_filter_keyboard_for_session(session),
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_upload_metric(deps, "document")

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
    validation_error = _validate_session_for_upload(session, kind, deps.settings.max_session_files)
    if validation_error is not None:
        await message.reply_text(validation_error)
        return

    _save_uploaded_file(session, build_session_file(document.file_id, document.file_name, kind), deps)

    if kind == FileKind.IMAGE:
        _schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)
        return

    _cancel_pending_image_notification(user.id, deps)
    await message.reply_text(
        f"File ricevuto.\n{build_session_recap(session)}",
        reply_markup=_filter_keyboard_for_session(session),
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await _prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    _record_upload_metric(deps, "photo")

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
    validation_error = _validate_session_for_upload(session, FileKind.IMAGE, deps.settings.max_session_files)
    if validation_error is not None:
        await message.reply_text(validation_error)
        return

    generated_name = f"foto_{len(session.files) + 1}.jpg"
    _save_uploaded_file(session, build_session_file(best_photo.file_id, generated_name, FileKind.IMAGE), deps)

    _schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)


async def handle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await _safe_answer_callback(query)

    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(_build_service_unavailable_message())
        return
    await _maybe_notify_admins_about_new_user(user, context)

    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    action = (query.data or "").removeprefix("action:")
    _record_callback_metric(deps, f"action:{action}")
    try:
        resolved_action = SupportedAction(action)
    except ValueError:
        await query.edit_message_text(_invalid_callback_message())
        return
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

    if action == SupportedAction.PDF_SPLIT.value:
        session.pending_action = action
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(
            _build_pending_action_prompt(SupportedAction.PDF_SPLIT),
            reply_markup=build_split_output_keyboard(),
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

    if _is_image_pdf_action(resolved_action):
        await query.edit_message_text(
            _build_image_pdf_layout_prompt(user.id, deps),
            reply_markup=build_images_pdf_layout_keyboard(action),
        )
        return

    if not _has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return

    job = await _enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=resolved_action,
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
    await _safe_answer_callback(query)
    preset = (query.data or "").removeprefix("compress:")
    _record_callback_metric(deps, f"compress:{preset}")
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(_build_service_unavailable_message())
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
    try:
        compression_preset = CompressionPreset(preset)
    except ValueError:
        await query.edit_message_text(_invalid_callback_message())
        return

    job = await _enqueue_job(
        context=context,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=SupportedAction.PDF_COMPRESS,
        session=session,
        compression_preset=compression_preset,
    )
    deps.session_store.set_user_preference(user.id, "compression_preset", preset)
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        f"Compressione presa in carico. Job #{job.id} in coda.\nTi invio il PDF appena è pronto."
    )


async def handle_split_output_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await _safe_answer_callback(query)
    output_choice = (query.data or "").removeprefix("split_output:")
    _record_callback_metric(deps, f"split_output:{output_choice}")
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(_build_service_unavailable_message())
        return
    await _maybe_notify_admins_about_new_user(user, context)
    _cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    if SupportedAction.PDF_SPLIT not in infer_supported_actions(session):
        await query.edit_message_text(
            "Questa scelta non è più compatibile con la sessione corrente. "
            "Inviami un singolo PDF oppure usa /reset per ripartire."
        )
        return

    if not _has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return

    if output_choice == "zip":
        split_output_zip = True
        choice_label = "zip"
    elif output_choice == "files":
        split_output_zip = False
        choice_label = "pdf separati"
    else:
        await query.edit_message_text(_invalid_callback_message())
        return

    try:
        job = await _enqueue_job(
            context=context,
            user_id=user.id,
            chat_id=query.message.chat_id,
            reply_to_message_id=query.message.message_id,
            action=SupportedAction.PDF_SPLIT,
            session=session,
            split_output_zip=split_output_zip,
        )
    except ProcessingUserError as exc:
        await query.edit_message_text(f"{exc}\n\nInviami un singolo PDF e riprova.")
        return
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        _build_pending_action_queued_message(SupportedAction.PDF_SPLIT, job.id, choice_label)
    )


async def handle_result_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    query = update.callback_query
    await _safe_answer_callback(query)

    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.message.reply_text(_build_service_unavailable_message())
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
    _record_callback_metric(deps, f"result:{action.split(':', 1)[0]}")
    if action.startswith("undo_rotate:"):
        if not _has_capacity_for_new_job(user.id, deps):
            await query.message.reply_text(
                _build_job_queue_limit_message(deps.settings.max_active_jobs_per_user),
                reply_to_message_id=query.message.message_id,
            )
            return
        try:
            source_job_id = int(action.removeprefix("undo_rotate:"))
        except ValueError:
            await query.message.reply_text(
                _invalid_callback_message(),
                reply_to_message_id=query.message.message_id,
            )
            return
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

    if selected_action == SupportedAction.PDF_SPLIT:
        session.pending_action = selected_action.value
        session.touch()
        deps.session_store.save(session)
        await query.message.reply_text(
            _build_pending_action_prompt(selected_action),
            reply_to_message_id=query.message.message_id,
            reply_markup=build_split_output_keyboard(),
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
    await _safe_answer_callback(query)

    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.message.reply_text(UNAUTHORIZED_MESSAGE, reply_to_message_id=query.message.message_id)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.message.reply_text(
            _build_service_unavailable_message(),
            reply_to_message_id=query.message.message_id,
        )
        return
    await _maybe_notify_admins_about_new_user(user, context)

    try:
        _, action, raw_job_id = (query.data or "").split(":", 2)
        job_id = int(raw_job_id)
    except (TypeError, ValueError):
        await query.message.reply_text("Richiesta non valida.", reply_to_message_id=query.message.message_id)
        return
    _record_callback_metric(deps, f"history:{action}")

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
    await _safe_answer_callback(query)

    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(_build_service_unavailable_message())
        return
    await _maybe_notify_admins_about_new_user(user, context)

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    degrees = int((query.data or "").removeprefix("rotate:"))
    _record_callback_metric(deps, f"rotate:{degrees}")
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
    await _safe_answer_callback(query)

    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(_build_service_unavailable_message())
        return
    await _maybe_notify_admins_about_new_user(user, context)

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    try:
        _, layout_choice, action_name = (query.data or "").split(":", 2)
        action = SupportedAction(action_name)
    except (TypeError, ValueError):
        await query.edit_message_text(_invalid_callback_message())
        return
    _record_callback_metric(deps, f"images_pdf_layout:{layout_choice}")
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
    await _safe_answer_callback(query)

    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await query.edit_message_text(_build_service_unavailable_message())
        return
    await _maybe_notify_admins_about_new_user(user, context)

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return

    try:
        _, margin_choice, action_name = (query.data or "").split(":", 2)
        action = SupportedAction(action_name)
    except (TypeError, ValueError):
        await query.edit_message_text(_invalid_callback_message())
        return
    _record_callback_metric(deps, f"images_pdf_margin:{margin_choice}")
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
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    if _is_service_paused(deps) and not _is_admin(user.id if user else None, deps.settings):
        await message.reply_text(_build_service_unavailable_message())
        return
    await _maybe_notify_admins_about_new_user(user, context)

    text = (message.text or "").strip()
    menu_text = LEGACY_MENU_LABELS.get(text, text)

    if menu_text == "Sessione attiva" or text == "Mostra sessione":
        await status_command(update, context)
        return
    if menu_text == "Storico lavori":
        await history_command(update, context)
        return
    if menu_text == "Azzera sessione":
        await reset_command(update, context)
        return
    if menu_text == "Guida rapida" or text == "Cosa posso fare":
        await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())
        return
    session = deps.session_store.get(user.id)
    if _is_latest_job_rerun_text(text) and not (session is not None and session.files):
        await _rerun_latest_user_job(
            context=context,
            deps=deps,
            user_id=user.id,
            message=message,
        )
        return

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

        text_request = _resolve_text_request(session, text)
        if text_request is not None:
            if text_request.kind == "clarify":
                await message.reply_text(text_request.message or "Dimmi meglio quale operazione vuoi eseguire.")
                return

            if text_request.kind == "pending" and text_request.action is not None:
                session.pending_action = text_request.action.value
                session.touch()
                deps.session_store.save(session)
                if text_request.action == SupportedAction.PDF_SPLIT:
                    await message.reply_text(
                        text_request.message or _build_pending_action_prompt(text_request.action),
                        reply_markup=build_split_output_keyboard(),
                    )
                else:
                    await message.reply_text(text_request.message or _build_pending_action_prompt(text_request.action))
                return

            action = text_request.action
            if action is None:
                await message.reply_text("Non ho capito abbastanza bene la richiesta. Prova a riformularla in modo piu diretto.")
                return
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
                compression_preset=text_request.compression_preset,
                rotate_degrees=text_request.rotate_degrees,
                page_selection=text_request.page_selection,
                watermark_text=text_request.watermark_text,
                split_output_zip=text_request.split_output_zip if text_request.split_output_zip is not None else True,
            )
            deps.session_store.delete(user.id)
            if action == SupportedAction.PDF_SPLIT:
                await message.reply_text(
                    _build_pending_action_queued_message(
                        action,
                        job.id,
                        "zip" if text_request.split_output_zip else "pdf separati",
                    )
                )
            elif text_request.page_selection or text_request.watermark_text:
                raw_value = text_request.page_selection or text_request.watermark_text or ""
                await message.reply_text(_build_pending_action_queued_message(action, job.id, str(raw_value)))
            elif text_request.rotate_degrees is not None:
                await message.reply_text(
                    f"Rotazione manuale presa in carico di {text_request.rotate_degrees} gradi. "
                    f"Job #{job.id} in coda.\nTi invio il PDF appena e pronto."
                )
            else:
                await message.reply_text(
                    _build_text_request_queued_message(action, job.id, text_request.compression_preset)
                )
            return

    quick_action_guidance = _build_quick_action_guidance(session, menu_text)
    if quick_action_guidance is not None:
        await message.reply_text(quick_action_guidance, reply_markup=build_main_menu_keyboard())
        return

    if _mentions_context_reference(text):
        await message.reply_text(
            _build_missing_context_reference_message(deps, user.id),
            reply_markup=build_main_menu_keyboard(),
        )
        return

    await message.reply_text(
        "Per iniziare, inviami immagini o PDF. Se vuoi una guida rapida, usa /help oppure il menu qui sotto.",
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
        last_sent_at = _parse_meta_datetime(deps.session_store.get_meta(_new_user_admin_meta_key(admin_user_id, "last_sent_at")))
        pending_count_key = _new_user_admin_meta_key(admin_user_id, "pending_count")
        now = datetime.now(timezone.utc)
        if last_sent_at is not None and (now - last_sent_at).total_seconds() < _NEW_USER_NOTIFICATION_COOLDOWN_SECONDS:
            _increment_meta_counter(deps, pending_count_key)
            continue

        pending_count = _get_meta_counter(deps, pending_count_key)
        admin_notification_text = notification_text
        if pending_count > 0:
            admin_notification_text = (
                f"{notification_text}\n\n"
                f"Nel frattempo altri {pending_count} utenti nuovi hanno già aperto il bot."
            )
        try:
            await _safe_send_message(
                context.bot,
                chat_id=admin_user_id,
                text=admin_notification_text,
                deps=deps,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            deps.session_store.set_meta(_new_user_admin_meta_key(admin_user_id, "last_sent_at"), now.isoformat())
            deps.session_store.set_meta(pending_count_key, "0")
        except TelegramError:
            logger.exception("Impossibile inviare la notifica nuovo utente all'admin %s", admin_user_id)


def _build_new_user_notification(user: User) -> str:
    timestamp = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y alle %H:%M:%S")
    full_name_value = getattr(user, "full_name", None) or " ".join(
        part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part
    )
    full_name = html.escape(full_name_value or "Sconosciuto")
    username_value = getattr(user, "username", None)
    username = f"@{html.escape(username_value)}" if username_value else "non disponibile"
    profile_link = f'<a href="tg://user?id={user.id}">Apri profilo Telegram</a>'
    public_link = f' | <a href="https://t.me/{html.escape(username_value)}">Apri username</a>' if username_value else ""

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
        f"- Dividi PDF: {stats.pdf_split_total}\n"
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


def _build_admin_queue_report(deps: BotDependencies) -> str:
    stats = deps.session_store.build_admin_stats()
    queued_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.QUEUED,))
    running_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.RUNNING,))
    recent_failed_jobs = deps.session_store.list_recent_jobs(limit=3, statuses=(JobStatus.FAILED,))
    recent_failed_actions = deps.session_store.list_failed_actions(limit=3, since_minutes=max(5, deps.settings.admin_alert_window_minutes))
    queue_backlog = deps.job_queue.qsize()
    queued_block = "\n".join(_format_job_line(job) for job in queued_jobs) or "- Nessun job in coda persistente"
    running_block = "\n".join(_format_job_line(job) for job in running_jobs) or "- Nessun job in esecuzione"
    failed_block = "\n".join(_format_job_line(job) for job in recent_failed_jobs) or "- Nessun job fallito recente"
    failed_actions_block = "\n".join(
        f"- {_action_label(entry.action)}: {entry.total}"
        for entry in recent_failed_actions
    ) or "- Nessun pattern di errore recente"
    return (
        "Coda operativa DocMolder\n"
        f"- Service mode: {_build_service_status_label(deps)}\n"
        f"- Coda in memoria: {queue_backlog}\n"
        f"- Job queued persistiti: {stats.jobs_queued}\n"
        f"- Job running persistiti: {stats.jobs_running}\n"
        f"- Sessioni attive: {stats.active_sessions}\n\n"
        "Ultimi job in coda:\n"
        f"{queued_block}\n\n"
        "Job in lavorazione:\n"
        f"{running_block}\n\n"
        "Ultimi job falliti:\n"
        f"{failed_block}\n\n"
        "Errori ricorrenti recenti:\n"
        f"{failed_actions_block}"
    )


def _build_admin_health_report(deps: BotDependencies) -> str:
    settings = deps.settings
    runtime_dir = settings.runtime_dir
    database_path = settings.database_path
    backup_dir = getattr(settings, "sqlite_backup_dir", runtime_dir / "backups")
    runtime_status = "ok" if runtime_dir.exists() else "mancante"
    db_status = "ok" if database_path.exists() else "mancante"
    backup_status = "ok" if backup_dir.exists() else "mancante"
    db_size = _format_bytes(database_path.stat().st_size) if database_path.exists() else "0 B"
    backup_count = len(list(backup_dir.glob("*"))) if backup_dir.exists() else 0
    disk_snapshot = _runtime_disk_snapshot(runtime_dir)
    disk_block = (
        f"- Disco totale: {_format_bytes(disk_snapshot[0])}\n"
        f"- Disco usato: {_format_bytes(disk_snapshot[1])}\n"
        f"- Disco libero: {_format_bytes(disk_snapshot[2])}"
        if disk_snapshot is not None
        else "- Disco: non disponibile"
    )
    worker_status = "attivo" if deps.job_worker_task is not None and not deps.job_worker_task.done() else "fermato"
    cleanup_status = "attivo" if deps.cleanup_task is not None and not deps.cleanup_task.done() else "fermato"
    admin_status = "attivo" if deps.admin_report_task is not None and not deps.admin_report_task.done() else "fermato"
    return (
        "Health operativo DocMolder\n"
        f"- Service mode: {_build_service_status_label(deps)}\n"
        f"- Runtime dir: {runtime_dir} ({runtime_status})\n"
        f"- Database SQLite: {database_path} ({db_status}, {db_size})\n"
        f"- Backup dir: {backup_dir} ({backup_status}, {backup_count} file)\n"
        f"- Worker job: {worker_status}\n"
        f"- Cleanup schedulato: {cleanup_status}\n"
        f"- Report admin schedulati: {admin_status}\n"
        f"- Coda in memoria: {deps.job_queue.qsize()}\n"
        f"{disk_block}"
    )


def _build_admin_maintenance_overview(deps: BotDependencies) -> str:
    max_running_age_seconds = int(getattr(deps.settings, "health_max_running_job_age_seconds", 3600))
    health = build_health_report(
        deps.settings,
        max_queued_jobs=getattr(deps.settings, "health_max_queued_jobs", 20),
        max_running_jobs=getattr(deps.settings, "health_max_running_jobs", 5),
        max_running_job_age_seconds=max_running_age_seconds,
        max_runtime_dir_bytes=getattr(deps.settings, "health_max_runtime_dir_bytes", 2_147_483_648),
        max_backup_age_seconds=getattr(deps.settings, "health_max_backup_age_seconds", 172800),
    )
    stale_jobs = deps.session_store.list_stale_running_jobs(max_age_seconds=max_running_age_seconds, limit=5)
    pending_users = [
        user_id for user_id, status in _list_dynamic_access_statuses(deps) if status == _ACCESS_STATUS_PENDING
    ]
    recent_audit_entries = deps.session_store.list_audit_log_entries(limit=5)
    stale_block = "\n".join(_format_job_line(job) for job in stale_jobs) or "- Nessun running stale"
    pending_block = "\n".join(f"- Utente {user_id}" for user_id in pending_users[:5]) or "- Nessuna richiesta pending"
    audit_block = "\n".join(
        f"- {entry.event_type}: {entry.outcome} ({entry.actor_user_id or 'sistema'} -> {entry.target_user_id or '-'})"
        for entry in recent_audit_entries
    ) or "- Nessun evento audit"
    alerts = ", ".join(health.get("alerts", [])) or "nessun alert"
    warnings = ", ".join(health.get("warnings", [])) or "nessun warning"
    return (
        "Manutenzione operativa DocMolder\n"
        f"- Health: {health['status']}\n"
        f"- Alert: {alerts}\n"
        f"- Warning: {warnings}\n"
        f"- Runtime size: {_format_bytes(int(health['runtime']['size_bytes']))}\n"
        f"- Backup disponibili: {health['backup']['count']}\n"
        f"- Ultimo backup age seconds: {health['backup']['latest_age_seconds']}\n\n"
        "Running stale:\n"
        f"{stale_block}\n\n"
        "Richieste accesso pending:\n"
        f"{pending_block}\n\n"
        "Audit recente:\n"
        f"{audit_block}"
    )


def _build_access_status_message(deps: BotDependencies, user_id: int) -> str:
    session = deps.session_store.get(user_id)
    active_jobs = deps.session_store.count_active_jobs_for_user(user_id)
    recent_jobs = deps.session_store.list_user_jobs(user_id, limit=1)
    last_job = recent_jobs[0] if recent_jobs else None
    dynamic_status = _get_dynamic_access_status(deps, user_id) or "nessuno"
    lines = [
        "Stato accesso DocMolder",
        f"- Service mode: {_build_service_status_label(deps)}",
        f"- Accesso account: {'consentito' if _is_authorized_for_deps(user_id, deps) else 'non consentito'}",
        f"- Stato richiesta: {dynamic_status}",
        f"- Job attivi: {active_jobs}/{deps.settings.max_active_jobs_per_user}",
        f"- Sessione corrente: {'attiva' if session is not None and session.files else 'vuota'}",
    ]
    if session is not None and session.files:
        lines.append(f"- File in sessione: {len(session.files)}")
        if session.pending_action:
            lines.append(f"- Input atteso: {_action_label(session.pending_action)}")
    if last_job is not None:
        lines.append(
            f"- Ultimo job: #{last_job.id} {_action_label(last_job.action)} ({_format_job_status(last_job.status).lower()})"
        )
    else:
        lines.append("- Ultimo job: nessuno")
    lines.append("- Self-service rapido: usa /last per rilanciare l'ultimo job e /history per vedere i dettagli recenti.")
    return "\n".join(lines)


def _build_policy_message(deps: BotDependencies) -> str:
    return (
        "Policy sintetica DocMolder\n\n"
        "Uso supportato:\n"
        "- invia PDF, immagini o scansioni nella chat privata con il bot\n"
        "- ogni richiesta deve essere una trasformazione documentale chiara e circoscritta\n\n"
        "Dati e retention:\n"
        "- i file caricati servono solo per creare il risultato richiesto\n"
        f"- le directory job temporanee vengono pulite dopo circa {deps.settings.stale_job_retention_hours} ore\n"
        "- il database conserva metadati tecnici dei job, preferenze minime, audit admin e metriche operative\n"
        "- il contenuto dei documenti non viene scritto nei log e non va inserito in issue, test o report\n\n"
        "Limiti operativi:\n"
        f"- file massimo: {deps.settings.max_file_size_mb} MB\n"
        f"- file per sessione: {deps.settings.max_session_files}\n"
        f"- job attivi per utente: {deps.settings.max_active_jobs_per_user}\n"
        f"- upload rapido: {deps.settings.upload_burst_limit} file in {deps.settings.upload_burst_window_seconds} secondi\n\n"
        "Accesso:\n"
        "- se il bot è ristretto, usa /request_access per chiedere l'abilitazione\n"
        "- in manutenzione i nuovi job utente sono sospesi, ma restano disponibili policy e richiesta accesso"
    )


def _parse_target_user_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    raw_args = [str(arg).strip() for arg in getattr(context, "args", []) if str(arg).strip()]
    if not raw_args:
        return None
    try:
        return int(raw_args[0])
    except ValueError:
        return None


async def _notify_admins_about_access_request(
    user: User,
    context: ContextTypes.DEFAULT_TYPE,
    deps: BotDependencies,
) -> None:
    if not deps.settings.admin_user_ids:
        return
    full_name = html.escape(
        getattr(user, "full_name", None)
        or " ".join(part for part in [user.first_name, user.last_name] if part)
        or "Sconosciuto"
    )
    username = f"@{html.escape(user.username)}" if user.username else "non disponibile"
    text = (
        "Richiesta accesso DocMolder\n"
        f"ID utente: <code>{user.id}</code>\n"
        f"Nome: {full_name}\n"
        f"Username: {username}"
    )
    for admin_user_id in deps.settings.admin_user_ids:
        try:
            await _safe_send_message(
                context.bot,
                chat_id=admin_user_id,
                text=text,
                deps=deps,
                parse_mode=ParseMode.HTML,
                reply_markup=build_access_review_keyboard(user.id),
                disable_web_page_preview=True,
            )
        except TelegramError:
            logger.exception("Impossibile inviare richiesta accesso all'admin %s", admin_user_id)


def _resolve_job_selector(deps: BotDependencies, selector: str) -> JobRecord | None:
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


def _resolve_user_job_selector(deps: BotDependencies, user_id: int, selector: str) -> JobRecord | None:
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
    return {
        "photo": "foto",
        "document": "documenti",
    }.get(name, name)


def _build_telegram_metrics_report(deps: BotDependencies) -> str:
    raw_meta = deps.session_store.list_meta(_TELEGRAM_METRIC_PREFIX)
    command_entries = _extract_metric_entries(raw_meta, f"{_TELEGRAM_METRIC_PREFIX}command:")
    callback_entries = _extract_metric_entries(raw_meta, f"{_TELEGRAM_METRIC_PREFIX}callback:")
    upload_entries = _extract_metric_entries(raw_meta, f"{_TELEGRAM_METRIC_PREFIX}upload:")
    command_block = "\n".join(f"- /{name}: {count}" for name, count in command_entries) or "- Nessun comando registrato ancora"
    callback_block = "\n".join(f"- {name}: {count}" for name, count in callback_entries[:8]) or "- Nessuna callback rilevata ancora"
    upload_block = "\n".join(
        f"- {_format_upload_metric_name(name)}: {count}" for name, count in upload_entries
    ) or "- Nessun upload registrato ancora"
    return (
        "Metriche Telegram DocMolder\n"
        "Comandi:\n"
        f"{command_block}\n\n"
        "Upload:\n"
        f"{upload_block}\n\n"
        "Retry Telegram:\n"
        f"- sendMessage rate limit: {_get_meta_counter(deps, f'{_TELEGRAM_METRIC_PREFIX}retry_after:sendMessage')}\n"
        f"- sendDocument rate limit: {_get_meta_counter(deps, f'{_TELEGRAM_METRIC_PREFIX}retry_after:sendDocument')}\n"
        f"- sendMessage network retry: {_get_meta_counter(deps, f'{_TELEGRAM_METRIC_PREFIX}network_retry:sendMessage')}\n"
        f"- sendDocument network retry: {_get_meta_counter(deps, f'{_TELEGRAM_METRIC_PREFIX}network_retry:sendDocument')}\n\n"
        "Callback osservate (top):\n"
        f"{callback_block}"
    )


async def _handle_start_payload(
    payload: str,
    deps: BotDependencies,
    user_id: int,
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if payload == "help":
        await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())
        return True
    if payload == "history":
        jobs = deps.session_store.list_user_jobs(user_id, limit=5)
        if not jobs:
            await message.reply_text(
                "Non hai ancora uno storico lavori. Inviami immagini o PDF e terrò traccia degli ultimi job qui.",
                reply_markup=build_main_menu_keyboard(),
            )
        else:
            await message.reply_text(
                _build_user_history_summary(jobs),
                reply_markup=build_history_keyboard([job.id for job in jobs]),
            )
        return True
    if payload == "status":
        session = deps.session_store.get(user_id)
        if session is None or not session.files:
            await message.reply_text(SESSION_EMPTY_MESSAGE, reply_markup=build_main_menu_keyboard())
        else:
            await message.reply_text(
                build_session_recap(session),
                reply_markup=_filter_keyboard_for_session(session),
            )
        return True
    if payload == "access":
        await message.reply_text(_build_access_status_message(deps, user_id), reply_markup=build_main_menu_keyboard())
        return True
    if payload == "last":
        recent_jobs = deps.session_store.list_user_jobs(user_id, limit=1)
        if not recent_jobs:
            await message.reply_text(
                "Non ho ancora un job da rilanciare per te. Inviami immagini o PDF e poi potrò ripetere l'ultimo flusso.",
                reply_markup=build_main_menu_keyboard(),
            )
            return True
        if not _has_capacity_for_new_job(user_id, deps):
            await message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
            return True
        source_job = recent_jobs[0]
        rerun_job = await _enqueue_job_from_existing_payload(
            context=context,
            source_job=source_job,
            reply_to_message_id=message.message_id,
        )
        await message.reply_text(_build_history_rerun_message(source_job, rerun_job.id))
        return True
    if payload.startswith("retry_"):
        selector = payload.removeprefix("retry_")
        source_job = _resolve_user_job_selector(deps, user_id, selector)
        if source_job is None:
            await message.reply_text("Non riesco a trovare quel job da rilanciare.")
            return True
        if not _has_capacity_for_new_job(user_id, deps):
            await message.reply_text(_build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
            return True
        rerun_job = await _enqueue_job_from_existing_payload(
            context=context,
            source_job=source_job,
            reply_to_message_id=message.message_id,
        )
        await message.reply_text(_build_history_rerun_message(source_job, rerun_job.id))
        return True
    return False


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


def _action_label(action: PendingActionValue) -> str:
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
    application.add_handler(CommandHandler("last", last_command))
    application.add_handler(CommandHandler("access", access_command))
    application.add_handler(CommandHandler("policy", policy_command))
    application.add_handler(CommandHandler("privacy", policy_command))
    application.add_handler(CommandHandler("request_access", request_access_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("maintenance_overview", maintenance_overview_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("metrics", metrics_command))
    application.add_handler(CommandHandler("job", job_command))
    application.add_handler(CommandHandler("retry", retry_command))
    application.add_handler(CommandHandler("approve_user", access_review_command))
    application.add_handler(CommandHandler("reject_user", access_review_command))
    application.add_handler(CommandHandler("suspend_user", access_review_command))
    application.add_handler(CommandHandler("reactivate_user", access_review_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(handle_access_review_callback, pattern=r"^access:"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin:"))
    application.add_handler(CallbackQueryHandler(handle_history_callback, pattern=r"^history:"))
    application.add_handler(CallbackQueryHandler(handle_rotate_callback, pattern=r"^rotate:"))
    application.add_handler(CallbackQueryHandler(handle_result_action_callback, pattern=r"^result:"))
    application.add_handler(CallbackQueryHandler(handle_compression_callback, pattern=r"^compress:"))
    application.add_handler(CallbackQueryHandler(handle_split_output_callback, pattern=r"^split_output:"))
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
    if job.action.startswith("images_to_pdf"):
        detail_lines.append("Impaginazione: A4" if payload.image_pdf_use_a4 else "Impaginazione: formato originale")
    if job.action == SupportedAction.PDF_SPLIT.value:
        detail_lines.append("Output divisione: ZIP unico" if payload.split_output_zip else "Output divisione: PDF separati")
    detail_lines.append("Rotazione automatica PDF: attiva" if payload.auto_rotate_pdf else "Rotazione automatica PDF: disattiva")
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
    if source_job.action == SupportedAction.PDF_SPLIT.value:
        raw_value = "zip" if payload.split_output_zip else "pdf separati"
        base_message = _build_pending_action_queued_message(SupportedAction.PDF_SPLIT, job_id, raw_value)
        return f"Ripeto il job #{source_job.id} dal tuo storico.\n{base_message}"
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
    if result.additional_outputs:
        return result.message
    if not result.output_name.lower().endswith(".pdf"):
        return result.message

    followup_actions = infer_result_followup_actions(source_action)
    if not followup_actions:
        return f"{result.message}\n\nPuoi anche usare /last per ripetere il flusso o /access per vedere stato e sessione."

    quick_labels = ", ".join(get_action_label(action) for action in followup_actions[:3])
    return (
        f"{result.message}\n\n"
        f"Se vuoi, puoi continuare su questo PDF con: {quick_labels}.\n"
        "Self-service rapido: /last per ripetere l'ultimo job, /access per vedere stato e sessione."
    )


def _build_result_followup_keyboard(
    result: ProcessingResult,
    source_action: SupportedAction | None,
    source_job_id: int | None,
) -> InlineKeyboardMarkup | None:
    if result.additional_outputs:
        return None
    if not result.output_name.lower().endswith(".pdf"):
        return None
    return build_result_pdf_keyboard(
        quick_actions=infer_result_followup_actions(source_action),
        undo_rotation_job_id=source_job_id if result.auto_rotation_applied else None,
    )




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
        enqueue_kwargs: PendingActionEnqueueKwargs = {}
        if pending_action in {
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
                    "Non ho capito di quanto vuoi ruotare il PDF.\n"
                    "Scrivimi `90`, `180` oppure `270` gradi, oppure frasi come `giralo a destra`."
                )
                return True

            job = await _enqueue_job(
                context=context,
                user_id=user_id,
                chat_id=chat_id,
                reply_to_message_id=reply_to_message_id,
                action=pending_action,
                session=session,
                rotate_degrees=rotate_degrees,
            )
            deps.session_store.delete(user_id)
            await update.effective_message.reply_text(
                f"Rotazione manuale presa in carico di {rotate_degrees} gradi. "
                f"Job #{job.id} in coda.\nTi invio il PDF appena e pronto."
            )
            return True
        elif pending_action == SupportedAction.PDF_WATERMARK:
            watermark_text = text.strip()
            if not watermark_text:
                await update.effective_message.reply_text(
                    "Il watermark testuale non puo essere vuoto. Scrivimi una parola o una frase breve, ad esempio BOZZA."
                )
                return True
            enqueue_kwargs["watermark_text"] = watermark_text
        elif pending_action == SupportedAction.PDF_SPLIT:
            keyword_text = _normalize_keyword_text(text)
            split_output_zip = _infer_split_output_zip(keyword_text, _tokenize_keyword_text(keyword_text))
            if split_output_zip is None:
                await update.effective_message.reply_text(
                    _build_pending_action_prompt(pending_action),
                    reply_markup=build_split_output_keyboard(),
                )
                return True
            enqueue_kwargs["split_output_zip"] = split_output_zip
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
    raw_value = (
        "zip"
        if enqueue_kwargs.get("split_output_zip") is True
        else "pdf separati"
        if enqueue_kwargs.get("split_output_zip") is False
        else enqueue_kwargs.get("page_selection") or enqueue_kwargs.get("watermark_text") or text
    )
    await update.effective_message.reply_text(_build_pending_action_queued_message(pending_action, job.id, str(raw_value)))
    return True


def _build_images_pdf_layout_pending_action(action: SupportedAction) -> PendingActionValue:
    return f"{_PENDING_IMAGES_PDF_LAYOUT_PREFIX}:{action.value}"


def _build_images_pdf_margin_pending_action(action: SupportedAction) -> PendingActionValue:
    return f"{_PENDING_IMAGES_PDF_MARGIN_PREFIX}:{action.value}"


def _extract_pending_images_pdf_action(pending_action: PendingActionValue, prefix: str) -> SupportedAction | None:
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




def _build_rerun_without_rotation_message(source_job: JobRecord, job_id: int) -> str:
    payload = JobPayload.from_json(source_job.payload_json)
    action = SupportedAction(source_job.action)
    base_message = _build_text_request_queued_message(action, job_id, payload.compression_preset)
    return f"Ripeto la stessa operazione senza rotazione automatica del PDF.\n{base_message}"




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
            await _maybe_send_admin_anomaly_alerts(application, deps)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Errore durante l'invio dei report admin periodici.")


def _run_cleanup_cycle(deps: BotDependencies) -> None:
    removed_dirs = deps.processor.cleanup_stale_job_dirs(deps.settings.stale_job_retention_hours)
    if removed_dirs:
        logger.info("Cleanup schedulato: rimosse %s cartelle temporanee residue.", removed_dirs)
    log_event(logger, logging.INFO, "cleanup_cycle_complete", removed_dirs=removed_dirs)


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
        require_new_users_or_completed_actions=True,
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
        await _safe_send_message(application.bot, chat_id=admin_user_id, text=report_text, deps=deps)
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


async def _maybe_send_admin_anomaly_alerts(application: Application, deps: BotDependencies) -> None:
    if not deps.settings.admin_user_ids:
        return

    now = datetime.now(timezone.utc)
    for alert in _detect_admin_anomaly_alerts(deps):
        if not _should_send_admin_alert(deps, alert["key"], alert["signature"], now):
            _increment_meta_counter(deps, _admin_alert_meta_key(alert["key"], "suppressed_count"))
            continue
        alert_text = _append_admin_alert_digest(deps, alert["key"], alert["text"])
        for admin_user_id in deps.settings.admin_user_ids:
            try:
                await _safe_send_message(application.bot, chat_id=admin_user_id, text=alert_text, deps=deps)
            except TelegramError:
                logger.exception("Impossibile inviare l'allerta admin %s a %s", alert["key"], admin_user_id)
        deps.session_store.set_meta(_admin_alert_meta_key(alert["key"], "last_signature"), alert["signature"])
        deps.session_store.set_meta(_admin_alert_meta_key(alert["key"], "last_sent_at"), now.isoformat())
        deps.session_store.set_meta(_admin_alert_meta_key(alert["key"], "suppressed_count"), "0")


def _detect_admin_anomaly_alerts(deps: BotDependencies) -> list[AdminAlertPayload]:
    settings = deps.settings
    window_minutes = max(5, settings.admin_alert_window_minutes)
    finished_jobs = deps.session_store.list_recent_jobs(
        limit=100,
        statuses=(JobStatus.SUCCEEDED, JobStatus.FAILED),
        since_minutes=window_minutes,
    )
    failed_jobs = [job for job in finished_jobs if job.status == JobStatus.FAILED]
    alerts: list[AdminAlertPayload] = []

    if finished_jobs and failed_jobs:
        failure_rate_percent = round((len(failed_jobs) / len(finished_jobs)) * 100)
        if (
            len(finished_jobs) >= settings.admin_alert_min_finished_jobs
            and failure_rate_percent >= settings.admin_alert_failure_rate_percent
        ):
            latest_failed_job_id = max(job.id for job in failed_jobs)
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
        failed_action_counts = deps.session_store.list_failed_actions(
            limit=5,
            since_minutes=window_minutes,
        )
        for action_stat in failed_action_counts:
            if action_stat.total < repeated_threshold:
                continue
            action_failed_jobs = [job for job in failed_jobs if job.action == action_stat.action][:5]
            latest_failed_job_id = max(job.id for job in action_failed_jobs)
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


def _should_send_admin_alert(
    deps: BotDependencies,
    key: str,
    signature: str,
    now: datetime,
) -> bool:
    last_signature = deps.session_store.get_meta(_admin_alert_meta_key(key, "last_signature"))
    if last_signature == signature:
        return False

    cooldown_minutes = max(1, deps.settings.admin_alert_cooldown_minutes)
    last_sent_raw = deps.session_store.get_meta(_admin_alert_meta_key(key, "last_sent_at"))
    last_sent_at = _parse_meta_datetime(last_sent_raw)
    if last_sent_at is None:
        return True
    return now - last_sent_at >= timedelta(minutes=cooldown_minutes)


def _build_failure_rate_alert_text(
    *,
    finished_jobs: list[JobRecord],
    failed_jobs: list[JobRecord],
    window_minutes: int,
    threshold_percent: int,
) -> str:
    failure_rate_percent = round((len(failed_jobs) / len(finished_jobs)) * 100)
    action_counts: dict[str, int] = {}
    for job in failed_jobs:
        action_counts[job.action] = action_counts.get(job.action, 0) + 1
    top_actions = "\n".join(
        f"- {_action_label(action)}: {total}"
        for action, total in sorted(action_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
    )
    recent_block = "\n".join(_format_job_line(job) for job in failed_jobs[:3])
    return (
        "Allerta admin DocMolder\n"
        f"Segnale: tasso di fallimento anomalo negli ultimi {window_minutes} minuti.\n"
        f"- Job conclusi: {len(finished_jobs)}\n"
        f"- Job falliti: {len(failed_jobs)} ({failure_rate_percent}%)\n"
        f"- Soglia configurata: {threshold_percent}%\n\n"
        "Azioni coinvolte:\n"
        f"{top_actions}\n\n"
        "Ultimi job falliti:\n"
        f"{recent_block}"
    )


def _build_repeated_failures_alert_text(
    *,
    action_stat: AdminActionStat,
    failed_jobs: list[JobRecord],
    window_minutes: int,
    threshold_count: int,
) -> str:
    recent_block = "\n".join(_format_job_line(job) for job in failed_jobs)
    return (
        "Allerta admin DocMolder\n"
        f"Segnale: errori ripetuti su {_action_label(action_stat.action)} negli ultimi {window_minutes} minuti.\n"
        f"- Job falliti per questa azione: {action_stat.total}\n"
        f"- Soglia configurata: {threshold_count}\n\n"
        "Ultimi job falliti per questa azione:\n"
        f"{recent_block}"
    )


def _admin_alert_meta_key(key: str, suffix: str) -> str:
    return f"admin_alert:{key}:{suffix}"


def _append_admin_alert_digest(deps: BotDependencies, key: str, text: str) -> str:
    suppressed_count = _get_meta_counter(deps, _admin_alert_meta_key(key, "suppressed_count"))
    if suppressed_count <= 0:
        return text
    return f"{text}\n\nNel frattempo ho soppresso {suppressed_count} alert simili per evitare spam."


def _parse_meta_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


async def _process_job(application: Application, job_id: int) -> None:
    deps: BotDependencies = application.bot_data["deps"]
    job = deps.session_store.get_job(job_id)
    if job is None:
        return

    deps.session_store.mark_job_running(job_id)
    job = deps.session_store.get_job(job_id)
    if job is None:
        return
    log_event(logger, logging.INFO, "job_started", job_id=job.id, user_id=job.user_id, action=job.action)

    await _safe_send_message(
        application.bot,
        chat_id=job.chat_id,
        text=_build_processing_started_message(SupportedAction(job.action), job.id),
        reply_to_message_id=job.reply_to_message_id,
        deps=deps,
    )

    job_dir = deps.processor.create_job_dir(job.user_id)
    started_monotonic = perf_counter()
    try:
        try:
            result = await _run_job_payload(application, job, job_dir)
        except ProcessingUserError as exc:
            deps.session_store.mark_job_failed(job.id, str(exc))
            log_event(
                logger,
                logging.WARNING,
                "job_failed",
                job_id=job.id,
                user_id=job.user_id,
                action=job.action,
                error_type=type(exc).__name__,
            )
            await _safe_send_message(
                application.bot,
                chat_id=job.chat_id,
                text=f"Job #{job.id} non riuscito.\n{exc}",
                reply_to_message_id=job.reply_to_message_id,
                deps=deps,
            )
            return
        except Exception:
            logger.exception("Errore durante il job %s", job.id)
            deps.session_store.mark_job_failed(job.id, GENERIC_ERROR_MESSAGE)
            log_event(
                logger,
                logging.ERROR,
                "job_failed",
                job_id=job.id,
                user_id=job.user_id,
                action=job.action,
                error_type="unexpected",
            )
            await _safe_send_message(
                application.bot,
                chat_id=job.chat_id,
                text=f"Job #{job.id} non riuscito.\n{GENERIC_ERROR_MESSAGE}",
                reply_to_message_id=job.reply_to_message_id,
                deps=deps,
            )
            return

        input_dir = job_dir / "input"
        input_bytes = _sum_file_sizes(input_dir.iterdir()) if input_dir.exists() else 0
        output_bytes = _sum_processing_result_sizes(result)
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
        log_event(
            logger,
            logging.INFO,
            "job_succeeded",
            job_id=job.id,
            user_id=job.user_id,
            action=job.action,
            processing_mode=result.processing_mode,
            duration_ms=duration_ms,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
        )
        result_message = await _send_result(
            application.bot,
            job.chat_id,
            job.reply_to_message_id,
            result,
            deps=deps,
            source_action=SupportedAction(job.action),
            source_job_id=job.id,
        )
        if not result.additional_outputs and result_message is not None and getattr(result_message, "document", None) is not None:
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
    deps: BotDependencies | None = None,
    source_action: SupportedAction | None = None,
    source_job_id: int | None = None,
    ):
    first_message = None
    with result.output_path.open("rb") as payload:
        first_message = await _telegram_api_call(
            "sendDocument",
            bot.send_document,
            _deps=deps,
            chat_id=chat_id,
            document=payload,
            filename=result.output_name,
            caption=_build_result_delivery_message(result, source_action),
            reply_to_message_id=reply_to_message_id,
            reply_markup=_build_result_followup_keyboard(result, source_action, source_job_id),
        )
    for output in result.additional_outputs:
        with output.path.open("rb") as payload:
            await _telegram_api_call(
                "sendDocument",
                bot.send_document,
                _deps=deps,
                chat_id=chat_id,
                document=payload,
                filename=output.name,
                reply_to_message_id=reply_to_message_id,
            )
    return first_message


def _sum_file_sizes(paths) -> int:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _sum_processing_result_sizes(result: ProcessingResult) -> int:
    paths = [result.output_path, *(output.path for output in result.additional_outputs)]
    return _sum_file_sizes(paths)
