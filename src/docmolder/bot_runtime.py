from __future__ import annotations
import asyncio
import html
import logging
import re
import shutil
import traceback
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from zoneinfo import ZoneInfo
from telegram import Document, InlineKeyboardMarkup, Message, Update, User
from telegram import MenuButtonCommands
from telegram.constants import ChatType, ParseMode
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import Application, ApplicationHandlerStop, ContextTypes
from docmolder.config import Settings
from docmolder.access_control import (
    ACCESS_STATUS_BLOCKED as _ACCESS_STATUS_BLOCKED,
    ACCESS_STATUS_PENDING as _ACCESS_STATUS_PENDING,
    ACCESS_STATUS_REJECTED as _ACCESS_STATUS_REJECTED,
    get_dynamic_access_status as _get_dynamic_access_status,
    is_admin as _is_admin,
    is_authorized_for_deps as _is_authorized_for_deps,
    set_dynamic_access_status as _set_dynamic_access_status,
)
from docmolder.branding import TELEGRAM_DESCRIPTION, TELEGRAM_NAME, TELEGRAM_SHORT_DESCRIPTION, build_telegram_commands
from docmolder.keyboards import (
    build_access_review_keyboard,
    build_admin_dashboard_keyboard,
    build_main_menu_keyboard,
    build_session_actions_keyboard,
)
from docmolder.logging_utils import log_event
from docmolder.messages import (
    ADMIN_ONLY_MESSAGE,
    SERVICE_UNAVAILABLE_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    build_pending_action_prompt,
    build_pending_action_queued_message,
    build_processing_started_message,
    build_text_request_queued_message,
)
from docmolder.models import CompressionPreset, FileKind, JobStatus, SupportedAction, UserSession
from docmolder.processing import DocumentProcessor
from docmolder.processing_models import A4_MARGIN_NARROW_PX, A4_MARGIN_NONE_PX, A4_MARGIN_WIDE_PX
from docmolder.retry import run_async_with_retry
from docmolder.action_catalog import SessionAnalysis, build_session_recap, infer_session_analysis
from docmolder.session_store_protocol import SessionStore
from docmolder.telegram_messaging import send_telegram_message
from docmolder.text_requests import _normalize_keyword_text

logger = logging.getLogger(__name__)
_TELEGRAM_TOKEN_IN_URL_RE = re.compile("/bot[^/]+/")
_build_pending_action_prompt = build_pending_action_prompt
_build_pending_action_queued_message = build_pending_action_queued_message
_build_processing_started_message = build_processing_started_message
_build_text_request_queued_message = build_text_request_queued_message
_PENDING_IMAGES_PDF_LAYOUT_PREFIX = "images_pdf_layout"
_PENDING_IMAGES_PDF_MARGIN_PREFIX = "images_pdf_margin"
_PENDING_DOCUMENT_PHOTO_MODE = "document_photo_mode"
_PENDING_PDF_SPLIT_GROUPS = "pdf_split_groups"
_PENDING_PDF_SPLIT_CHUNKS = "pdf_split_chunks"
_SERVICE_MODE_META_KEY = "service_mode"
_SERVICE_MODE_NORMAL = "normal"
_SERVICE_MODE_MAINTENANCE = "maintenance"
_TELEGRAM_RETRY_ATTEMPTS = 3
_TELEGRAM_METRIC_PREFIX = "telegram_metric:"
_UPLOAD_BURST_META_PREFIX = "upload_burst:"
_ADMIN_CALLBACK_REPLAY_WINDOW_SECONDS = 5
_NEW_USER_NOTIFICATION_COOLDOWN_SECONDS = 120
_BRANDING_SYNC_RETRY_AT_META_KEY = "branding_sync:retry_at"
_BRANDING_SYNC_DEFAULT_BACKOFF_SECONDS = 3600
_PRESET_CONFIRMATION_THRESHOLD = 2
_COMPRESSION_PRESET_KEY = "compression_preset"
_SPLIT_OUTPUT_KEY = "split_output"
_IMAGE_PDF_LAYOUT_KEY = "image_pdf_layout"
_IMAGE_PDF_MARGIN_KEY = "image_pdf_margin_px"
_EXCEL_SUFFIX_BY_MIME_TYPE = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel.sheet.macroenabled.12": ".xlsm",
    "application/vnd.ms-excel": ".xls",
}


class BotDependencies:
    def __init__(self, settings: Settings, session_store: SessionStore, processor: DocumentProcessor) -> None:
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
            record.args = tuple((_redact_sensitive_arg(arg) for arg in record.args))
        elif isinstance(record.args, dict):
            record.args = {key: _redact_sensitive_arg(value) for key, value in record.args.items()}
        if record.exc_info:
            record.exc_text = _format_safe_exception(record.exc_info)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = _redact_sensitive_text(record.exc_text)
        return True


def _redact_sensitive_arg(value: object) -> object:
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def _format_safe_exception(exc_info: tuple[type[BaseException], BaseException, TracebackType | None]) -> str:
    exception_type, _, exception_traceback = exc_info
    stack = ""
    if exception_traceback:
        stack = "".join(
            (
                f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n'
                for frame in traceback.extract_tb(exception_traceback)
            )
        )
    return f"Traceback (most recent call last):\n{stack}{exception_type.__name__}: <redacted>"


def _redact_sensitive_text(text: str) -> str:
    return _TELEGRAM_TOKEN_IN_URL_RE.sub("/bot<redacted>/", text)


def _configure_logging() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s - %(message)s", level=logging.INFO)
    sensitive_filter = SensitiveLogFilter()
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(sensitive_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _get_dependencies(context: ContextTypes.DEFAULT_TYPE) -> BotDependencies:
    return context.application.bot_data["deps"]


async def _private_chat_only(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or chat.type == ChatType.PRIVATE:
        return
    if update.effective_message is not None:
        await update.effective_message.reply_text(
            "Per proteggere i tuoi documenti, usa DocMolder solo nella chat privata con il bot."
        )
    raise ApplicationHandlerStop


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


def _record_user_choice(deps: BotDependencies, user_id: int, key: str, value: str) -> None:
    deps.session_store.set_user_preference(user_id, key, value)
    last_key = f"{key}:last"
    streak_key = f"{key}:streak"
    previous_value = deps.session_store.get_user_preference(user_id, last_key)
    previous_streak = deps.session_store.get_user_preference(user_id, streak_key)
    try:
        streak = int(previous_streak) if previous_streak is not None else 0
    except ValueError:
        streak = 0
    streak = streak + 1 if previous_value == value else 1
    deps.session_store.set_user_preference(user_id, last_key, value)
    deps.session_store.set_user_preference(user_id, streak_key, str(streak))
    if streak >= _PRESET_CONFIRMATION_THRESHOLD:
        deps.session_store.set_user_preset(user_id, key, value)


def _get_stored_compression_preset(deps: BotDependencies, user_id: int, *, preset_only: bool = False) -> str | None:
    stored = deps.session_store.get_user_preset(user_id, _COMPRESSION_PRESET_KEY)
    if stored is None and (not preset_only):
        stored = deps.session_store.get_user_preference(user_id, _COMPRESSION_PRESET_KEY)
    if stored in {item.value for item in CompressionPreset}:
        return stored
    return None


def _resolve_compression_preset_for_job(
    deps: BotDependencies, user_id: int, requested_preset: CompressionPreset | None
) -> CompressionPreset:
    if requested_preset is not None:
        return requested_preset
    stored = _get_stored_compression_preset(deps, user_id)
    if stored is not None:
        return CompressionPreset(stored)
    return CompressionPreset.MEDIUM


def _get_stored_split_output_choice(deps: BotDependencies, user_id: int, *, preset_only: bool = False) -> str | None:
    stored = deps.session_store.get_user_preset(user_id, _SPLIT_OUTPUT_KEY)
    if stored is None and (not preset_only):
        stored = deps.session_store.get_user_preference(user_id, _SPLIT_OUTPUT_KEY)
    if stored in {"zip", "files"}:
        return stored
    return None


def _record_split_output_choice(deps: BotDependencies, user_id: int, split_output_zip: bool) -> None:
    _record_user_choice(deps, user_id, _SPLIT_OUTPUT_KEY, "zip" if split_output_zip else "files")


def _get_stored_image_pdf_layout(deps: BotDependencies, user_id: int, *, preset_only: bool = False) -> str | None:
    stored = deps.session_store.get_user_preset(user_id, _IMAGE_PDF_LAYOUT_KEY)
    if stored is None and (not preset_only):
        stored = deps.session_store.get_user_preference(user_id, _IMAGE_PDF_LAYOUT_KEY)
    if stored in {"a4", "original"}:
        return stored
    return None


def _get_stored_image_pdf_margin(deps: BotDependencies, user_id: int, *, preset_only: bool = False) -> str | None:
    stored = deps.session_store.get_user_preset(user_id, _IMAGE_PDF_MARGIN_KEY)
    if stored is None and (not preset_only):
        stored = deps.session_store.get_user_preference(user_id, _IMAGE_PDF_MARGIN_KEY)
    if stored in {str(A4_MARGIN_WIDE_PX), str(A4_MARGIN_NARROW_PX), str(A4_MARGIN_NONE_PX)}:
        return stored
    return None


def _record_image_pdf_choice(
    deps: BotDependencies, user_id: int, *, image_pdf_use_a4: bool, image_pdf_margin_px: int
) -> None:
    _record_user_choice(deps, user_id, _IMAGE_PDF_LAYOUT_KEY, "a4" if image_pdf_use_a4 else "original")
    _record_user_choice(deps, user_id, _IMAGE_PDF_MARGIN_KEY, str(image_pdf_margin_px))


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
            event_type, actor_user_id=actor_user_id, target_user_id=target_user_id, outcome=outcome, detail=detail
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


def _retry_after_seconds(exc: Exception, default: int) -> int:
    value = getattr(exc, "retry_after", default)
    if isinstance(value, timedelta):
        value = value.total_seconds()
    return max(1, int(value))


async def _telegram_api_call(label: str, call, *args, **kwargs):
    deps = kwargs.pop("_deps", None)

    async def action():
        return await call(*args, **kwargs)

    def should_retry(exc: Exception) -> bool:
        return isinstance(exc, (RetryAfter, TimedOut, NetworkError))

    def delay_for_exception(exc: Exception, attempt_index: int) -> float | None:
        if isinstance(exc, RetryAfter):
            return float(_retry_after_seconds(exc, 1))
        return float(attempt_index + 1)

    def on_retry(exc: Exception, attempt_no: int, total_attempts: int, delay: float) -> None:
        if isinstance(exc, RetryAfter):
            logger.warning("Telegram rate limit su %s, ritento tra %ss", label, int(delay))
            if isinstance(deps, BotDependencies):
                _increment_meta_counter(deps, f"{_TELEGRAM_METRIC_PREFIX}retry_after:{label}")
        else:
            logger.warning(
                "Errore temporaneo Telegram su %s (%s), ritento tra %ss", label, type(exc).__name__, int(delay)
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
    return (usage.total, usage.used, usage.free)


async def _sync_telegram_branding(
    application: Application, settings: Settings, session_store: SessionStore | None = None
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
        retry_after = _retry_after_seconds(exc, _BRANDING_SYNC_DEFAULT_BACKOFF_SECONDS)
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
    return any((fragment in padded_text for fragment in rerun_fragments)) and any(
        (fragment in padded_text for fragment in contextual_fragments)
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
    return any((fragment in padded_text for fragment in context_fragments))


def _build_missing_context_reference_message(deps: BotDependencies, user_id: int) -> str:
    latest_jobs = deps.session_store.list_user_jobs(user_id, limit=1)
    if latest_jobs:
        return "Ho capito il riferimento, ma non ho una sessione attiva con un PDF sicuro su cui lavorare.\nApri /history per recuperare un job recente oppure reinviami il PDF preciso e riparto da quello."
    return "Ho capito il riferimento, ma non ho ancora un PDF attivo in questa chat.\nInviami il file e poi puoi scrivere frasi come `comprimi questo PDF` o `dividilo senza zip`."


def _filter_keyboard_for_session(
    session: UserSession, *, expanded: bool = False, analysis: SessionAnalysis | None = None
) -> InlineKeyboardMarkup | None:
    return build_session_actions_keyboard(session, expanded=expanded, analysis=analysis)


def _build_session_reply(
    session: UserSession, *, intro: str | None = None, expanded: bool = False
) -> tuple[str, InlineKeyboardMarkup | None]:
    analysis = infer_session_analysis(session)
    recap = build_session_recap(session, analysis=analysis)
    text = f"{intro}\n{recap}" if intro else recap
    return (text, _filter_keyboard_for_session(session, expanded=expanded, analysis=analysis))


def _is_image_pdf_action(action: SupportedAction) -> bool:
    return action in {
        SupportedAction.IMAGES_TO_PDF,
        SupportedAction.IMAGES_TO_PDF_CROP,
        SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
        SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
    }


def _infer_document_kind(document: Document) -> FileKind | None:
    mime_type = document.mime_type or ""
    file_name = (document.file_name or "").lower()
    suffix = Path(file_name).suffix.lower()
    if mime_type == "application/pdf" or suffix == ".pdf":
        return FileKind.PDF
    if mime_type.startswith("image/") or suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return FileKind.IMAGE
    if suffix == ".xlsb":
        return None
    if suffix in {".xlsx", ".xlsm", ".xls"} or mime_type in _EXCEL_SUFFIX_BY_MIME_TYPE:
        return FileKind.EXCEL
    return None


def _build_admin_keyboard(deps: BotDependencies) -> InlineKeyboardMarkup:
    from docmolder.admin_reporting import _is_periodic_admin_report_enabled

    available_statuses = {
        status
        for status in (JobStatus.FAILED, JobStatus.RUNNING, JobStatus.QUEUED, JobStatus.SUCCEEDED)
        if deps.session_store.list_recent_jobs(limit=1, statuses=(status,))
    }
    return build_admin_dashboard_keyboard(
        service_paused=_is_service_paused(deps),
        available_job_statuses=available_statuses,
        daily_reports_enabled=_is_periodic_admin_report_enabled(deps, "daily"),
        weekly_reports_enabled=_is_periodic_admin_report_enabled(deps, "weekly"),
    )


def _purge_expired_sessions(deps: BotDependencies) -> None:
    deps.session_store.purge_expired(deps.settings.session_ttl_minutes)


async def _prepare_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, require_admin: bool = False
) -> tuple[BotDependencies, User, Message] | None:
    deps = _get_dependencies(context)
    _purge_expired_sessions(deps)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return None
    is_allowed = _is_admin(user.id, deps.settings) if require_admin else _is_authorized_for_deps(user.id, deps)
    if not is_allowed:
        if require_admin:
            await message.reply_text(ADMIN_ONLY_MESSAGE)
        else:
            await _handle_unauthorized_access_attempt(user, context, deps, message)
        return None
    if not require_admin and _is_service_paused(deps) and (not _is_admin(user.id, deps.settings)):
        await message.reply_text(_build_service_unavailable_message())
        return None
    await _maybe_notify_admins_about_new_user(user, context)
    return (deps, user, message)


async def _handle_unauthorized_access_attempt(
    user: User, context: ContextTypes.DEFAULT_TYPE, deps: BotDependencies, message: Message
) -> None:
    deps.session_store.register_user(user.id, user.username, user.first_name, user.last_name)
    current_status = _get_dynamic_access_status(deps, user.id)
    if current_status == _ACCESS_STATUS_BLOCKED:
        await message.reply_text(
            "Il tuo accesso è sospeso. Contatta l'admin del bot per una riattivazione.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    if current_status == _ACCESS_STATUS_REJECTED:
        await message.reply_text(UNAUTHORIZED_MESSAGE, reply_markup=build_main_menu_keyboard())
        return
    if current_status != _ACCESS_STATUS_PENDING:
        _set_dynamic_access_status(deps, user.id, _ACCESS_STATUS_PENDING)
        _append_audit_log(deps, "request_access", actor_user_id=user.id, outcome="pending", target_user_id=user.id)
        await _notify_admins_about_access_request(user, context, deps)
        await message.reply_text(
            "Accesso non ancora attivo. Ho inviato una richiesta all'admin: quando viene approvata potrai usare il bot.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    await message.reply_text(
        "Accesso non ancora attivo. La richiesta è già in attesa di approvazione admin.",
        reply_markup=build_main_menu_keyboard(),
    )


def _parse_meta_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


async def _maybe_notify_admins_about_new_user(user: User | None, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user is None:
        return
    deps = _get_dependencies(context)
    if not deps.settings.admin_user_ids:
        return
    is_new = deps.session_store.register_user(
        user_id=user.id, username=user.username, first_name=user.first_name, last_name=user.last_name
    )
    if not is_new:
        return
    notification_text = _build_new_user_notification(user)
    for admin_user_id in deps.settings.admin_user_ids:
        last_sent_at = _parse_meta_datetime(
            deps.session_store.get_meta(_new_user_admin_meta_key(admin_user_id, "last_sent_at"))
        )
        pending_count_key = _new_user_admin_meta_key(admin_user_id, "pending_count")
        now = datetime.now(timezone.utc)
        if last_sent_at is not None and (now - last_sent_at).total_seconds() < _NEW_USER_NOTIFICATION_COOLDOWN_SECONDS:
            _increment_meta_counter(deps, pending_count_key)
            continue
        pending_count = _get_meta_counter(deps, pending_count_key)
        admin_notification_text = notification_text
        if pending_count > 0:
            admin_notification_text = (
                f"{notification_text}\n\nNel frattempo altri {pending_count} utenti nuovi hanno già aperto il bot."
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
        (part for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if part)
    )
    full_name = html.escape(full_name_value or "Sconosciuto")
    username_value = getattr(user, "username", None)
    username = f"@{html.escape(username_value)}" if username_value else "non disponibile"
    profile_link = f'<a href="tg://user?id={user.id}">Apri profilo Telegram</a>'
    public_link = f' | <a href="https://t.me/{html.escape(username_value)}">Apri username</a>' if username_value else ""
    return f"Nuovo utente al primo accesso su <b>DocMolder</b>.\nData e ora: {timestamp}\nID utente: <code>{user.id}</code>\nNome: {full_name}\nUsername: {username}\nLink: {profile_link}{public_link}"


async def _notify_admins_about_access_request(
    user: User, context: ContextTypes.DEFAULT_TYPE, deps: BotDependencies
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
