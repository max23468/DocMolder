from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

def _bot():
    from docmolder import bot

    return bot


from docmolder.keyboards import build_history_keyboard, build_main_menu_keyboard
from docmolder.messages import ADMIN_ONLY_MESSAGE, HELP_MESSAGE, MIXED_SESSION_MESSAGE, SESSION_EMPTY_MESSAGE, UNAUTHORIZED_MESSAGE, WELCOME_MESSAGE
from docmolder.models import FileKind, JobStatus
from docmolder.services import build_session_file, describe_session


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    if not _bot()._is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    await update.effective_message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=build_main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    if not _bot()._is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    await update.effective_message.reply_text(
        HELP_MESSAGE,
        reply_markup=build_main_menu_keyboard(),
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    if not _bot()._is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    jobs = deps.session_store.list_user_jobs(user.id, limit=5)
    if not jobs:
        await update.effective_message.reply_text(
            "Non hai ancora uno storico lavori. Inviami immagini o PDF e terrò traccia degli ultimi job qui.",
            reply_markup=build_main_menu_keyboard(),
        )
        return

    await update.effective_message.reply_text(
        _bot()._build_user_history_summary(jobs),
        reply_markup=build_history_keyboard([job.id for job in jobs]),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    if not _bot()._is_admin(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(ADMIN_ONLY_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    stats = deps.session_store.build_admin_stats()
    top_users = deps.session_store.list_top_users(limit=5, since_days=7)
    failed_actions = deps.session_store.list_failed_actions(limit=5, since_days=7)
    recent_failed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.FAILED,))
    recent_completed_jobs = deps.session_store.list_recent_jobs(limit=5, statuses=(JobStatus.SUCCEEDED,))
    await update.effective_message.reply_text(
        _bot()._build_admin_report(stats, top_users, failed_actions, recent_failed_jobs, recent_completed_jobs)
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    if not _bot()._is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    _bot()._cancel_pending_image_notification(user.id, deps)
    deps.session_store.delete(user.id)
    await update.effective_message.reply_text(
        "Sessione azzerata. Puoi inviarmi nuovi file quando vuoi.",
        reply_markup=build_main_menu_keyboard(),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    if not _bot()._is_authorized(user.id if user else None, deps.settings):
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await update.effective_message.reply_text(
            SESSION_EMPTY_MESSAGE,
            reply_markup=build_main_menu_keyboard(),
        )
        return

    extra_note = (
        f"\nSto aspettando un tuo input per: {_bot()._action_label(session.pending_action)}."
        if session.pending_action
        else ""
    )
    await update.effective_message.reply_text(
        f"{describe_session(session)}{extra_note}\nScegli cosa vuoi fare.",
        reply_markup=_bot()._filter_keyboard_for_session(session),
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    message = update.effective_message
    if not _bot()._is_authorized(user.id if user else None, deps.settings):
        await message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    document = message.document
    if document is None:
        return

    kind = _bot()._infer_document_kind(document)
    if kind is None:
        await message.reply_text("Per ora supporto solo PDF e immagini.")
        return

    if not _bot()._consume_upload_slot(user.id, deps):
        await message.reply_text(
            _bot()._build_upload_rate_limit_message(
                deps.settings.upload_burst_limit,
                deps.settings.upload_burst_window_seconds,
            )
        )
        return

    if _bot()._exceeds_file_size_limit(document.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_bot()._build_file_too_large_message(deps.settings.max_file_size_mb))
        return

    session = _bot()._get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text(_bot()._build_session_file_limit_message(deps.settings.max_session_files))
        return
    if session.files and any(item.kind != kind for item in session.files):
        await message.reply_text(MIXED_SESSION_MESSAGE)
        return

    session.files.append(build_session_file(document.file_id, document.file_name, kind))
    session.pending_action = None
    session.touch()
    deps.session_store.save(session)

    if kind == FileKind.IMAGE:
        _bot()._schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)
        return

    _bot()._cancel_pending_image_notification(user.id, deps)
    await message.reply_text(
        f"File ricevuto. {describe_session(session)}\nScegli la prossima azione.",
        reply_markup=_bot()._filter_keyboard_for_session(session),
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = _bot()._get_dependencies(context)
    _bot()._purge_expired_sessions(deps)
    user = update.effective_user
    message = update.effective_message
    if not _bot()._is_authorized(user.id if user else None, deps.settings):
        await message.reply_text(UNAUTHORIZED_MESSAGE)
        return
    await _bot()._maybe_notify_admins_about_new_user(user, context)

    photos = message.photo
    if not photos:
        return

    if not _bot()._consume_upload_slot(user.id, deps):
        await message.reply_text(
            _bot()._build_upload_rate_limit_message(
                deps.settings.upload_burst_limit,
                deps.settings.upload_burst_window_seconds,
            )
        )
        return

    best_photo = _bot()._pick_best_photo(photos)
    if _bot()._exceeds_file_size_limit(best_photo.file_size, deps.settings.max_file_size_mb):
        await message.reply_text(_bot()._build_file_too_large_message(deps.settings.max_file_size_mb))
        return

    session = _bot()._get_or_create_session(user.id, deps)
    if len(session.files) >= deps.settings.max_session_files:
        await message.reply_text(_bot()._build_session_file_limit_message(deps.settings.max_session_files))
        return
    if session.files and any(item.kind != FileKind.IMAGE for item in session.files):
        await message.reply_text(MIXED_SESSION_MESSAGE)
        return

    generated_name = f"foto_{len(session.files) + 1}.jpg"
    session.files.append(build_session_file(best_photo.file_id, generated_name, FileKind.IMAGE))
    session.pending_action = None
    session.touch()
    deps.session_store.save(session)

    _bot()._schedule_image_session_notification(chat_id=message.chat_id, user_id=user.id, context=context)
