from __future__ import annotations
from telegram import Message, Update
from telegram.ext import ContextTypes
from docmolder.access_control import is_admin as _is_admin, is_authorized_for_deps as _is_authorized_for_deps
from docmolder.keyboards import (
    build_compression_keyboard,
    build_document_photo_mode_keyboard,
    build_history_keyboard,
    build_images_pdf_layout_keyboard,
    build_images_pdf_margin_keyboard,
    build_main_menu_keyboard,
    build_rotate_keyboard,
    build_split_output_keyboard,
    build_delete_data_request_keyboard,
)
from docmolder.messages import (
    HELP_MESSAGE,
    PUBLIC_PRIVACY_URL,
    SESSION_EMPTY_MESSAGE,
    UNAUTHORIZED_MESSAGE,
    WELCOME_MESSAGE,
    build_job_queue_limit_message,
)
from docmolder.models import CompressionPreset, DocumentPhotoMode, SupportedAction
from docmolder.processing_models import A4_MARGIN_NARROW_PX, A4_MARGIN_NONE_PX, A4_MARGIN_WIDE_PX, ProcessingUserError
from docmolder.action_catalog import infer_supported_actions
from docmolder.text_requests import _build_quick_action_guidance, _resolve_text_request
import docmolder.bot_results as bot_results
import docmolder.bot_runtime as bot_runtime
import docmolder.bot_sessions as bot_sessions
import docmolder.job_flow as job_flow


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, user, message = prepared
    bot_runtime._record_command_metric(deps, "start")
    deep_link_payload = (context.args[0].strip() if getattr(context, "args", None) else "").lower()
    if deep_link_payload:
        handled = await _handle_start_payload(deep_link_payload, deps, user.id, message, context)
        if handled:
            return
    await message.reply_text(WELCOME_MESSAGE, reply_markup=build_main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prepared = await bot_runtime._prepare_message_handler(update, context)
    if prepared is None:
        return
    deps, _user, message = prepared
    bot_runtime._record_command_metric(deps, "help")
    await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())


async def handle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    bot_sessions._cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    action = (query.data or "").removeprefix("action:")
    bot_runtime._record_callback_metric(deps, f"action:{action}")
    if action in {"more", "less"}:
        session_text, session_keyboard = bot_runtime._build_session_reply(session, expanded=action == "more")
        await query.edit_message_text(session_text, reply_markup=session_keyboard)
        return
    try:
        resolved_action = SupportedAction(action)
    except ValueError:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    deps.session_store.record_flow_event(user.id, session.created_at.isoformat(), "action_selected", action)
    if action == SupportedAction.PDF_COMPRESS.value:
        session.pending_action = action
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(
            _build_compression_prompt(user.id, deps),
            reply_markup=build_compression_keyboard(
                bot_runtime._get_stored_compression_preset(deps, user.id, preset_only=True)
            ),
        )
        return
    if action == SupportedAction.PDF_ROTATE.value:
        session.pending_action = action
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(
            "Di quanti gradi vuoi ruotare tutte le pagine del PDF?", reply_markup=build_rotate_keyboard()
        )
        return
    if action == SupportedAction.DOCUMENT_PHOTO_FIX.value:
        session.pending_action = bot_runtime._PENDING_DOCUMENT_PHOTO_MODE
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(
            _build_document_photo_mode_prompt(), reply_markup=build_document_photo_mode_keyboard()
        )
        return
    if action == SupportedAction.PDF_SPLIT.value:
        session.pending_action = action
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(
            _build_split_output_prompt(user.id, deps),
            reply_markup=build_split_output_keyboard(
                bot_runtime._get_stored_split_output_choice(deps, user.id, preset_only=True)
            ),
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
        await query.edit_message_text(bot_runtime._build_pending_action_prompt(SupportedAction(action)))
        return
    if bot_runtime._is_image_pdf_action(resolved_action):
        session.pending_action = bot_sessions._build_images_pdf_layout_pending_action(resolved_action)
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(
            _build_image_pdf_layout_prompt(user.id, deps),
            reply_markup=build_images_pdf_layout_keyboard(
                action,
                preset_layout=bot_runtime._get_stored_image_pdf_layout(deps, user.id, preset_only=True),
                preset_margin_px=bot_runtime._get_stored_image_pdf_margin(deps, user.id, preset_only=True),
            ),
        )
        return
    if not job_flow.has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    job = await job_flow.enqueue_job(
        deps=deps,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=resolved_action,
        session=session,
    )
    deps.session_store.delete(user.id)
    await query.edit_message_text(bot_runtime._build_text_request_queued_message(resolved_action, job.id, None))


async def handle_compression_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    preset = (query.data or "").removeprefix("compress:")
    bot_runtime._record_callback_metric(deps, f"compress:{preset}")
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    bot_sessions._cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    if not job_flow.has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    try:
        compression_preset = CompressionPreset(preset)
    except ValueError:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    job = await job_flow.enqueue_job(
        deps=deps,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=SupportedAction.PDF_COMPRESS,
        session=session,
        compression_preset=compression_preset,
    )
    bot_runtime._record_user_choice(deps, user.id, bot_runtime._COMPRESSION_PRESET_KEY, preset)
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        f"Compressione presa in carico. Job #{job.id} in coda.\nTi invio il PDF appena è pronto."
    )


async def handle_quick_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    try:
        action = SupportedAction((query.data or "").removeprefix("quick:"))
    except ValueError:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    deps.session_store.record_flow_event(user.id, session.created_at.isoformat(), "action_selected", action.value)
    if action not in {SupportedAction.PDF_COMPRESS, SupportedAction.PDF_SPLIT} or action not in infer_supported_actions(session):
        await query.edit_message_text("Questa azione non è più compatibile con il lavoro corrente.")
        return
    if not job_flow.has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    kwargs = {}
    if action == SupportedAction.PDF_COMPRESS:
        kwargs["compression_preset"] = bot_runtime._resolve_compression_preset_for_job(deps, user.id, None)
    else:
        kwargs["split_output_zip"] = bot_runtime._get_stored_split_output_choice(deps, user.id) != "files"
    job = await job_flow.enqueue_job(
        deps=deps,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=action,
        session=session,
        **kwargs,
    )
    deps.session_store.delete(user.id)
    if action == SupportedAction.PDF_COMPRESS:
        await query.edit_message_text(
            bot_runtime._build_text_request_queued_message(action, job.id, kwargs["compression_preset"])
        )
    else:
        detail = "ZIP" if kwargs.get("split_output_zip") else "PDF separati"
        await query.edit_message_text(bot_runtime._build_pending_action_queued_message(action, job.id, detail))


async def handle_split_output_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    output_choice = (query.data or "").removeprefix("split_output:")
    bot_runtime._record_callback_metric(deps, f"split_output:{output_choice}")
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    bot_sessions._cancel_pending_image_notification(user.id, deps)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    if SupportedAction.PDF_SPLIT not in infer_supported_actions(session):
        await query.edit_message_text(
            "Questa scelta non è più compatibile con la sessione corrente. Inviami un singolo PDF oppure usa /reset per ripartire."
        )
        return
    if output_choice in {"groups", "chunks"}:
        session.pending_action = (
            bot_runtime._PENDING_PDF_SPLIT_GROUPS
            if output_choice == "groups"
            else bot_runtime._PENDING_PDF_SPLIT_CHUNKS
        )
        session.touch()
        deps.session_store.save(session)
        prompt = (
            "Scrivi i gruppi separati da |. Ogni pagina deve comparire una sola volta.\nEsempio: 1-3 | 4-6 | 7-10."
            if output_choice == "groups"
            else "Quante pagine vuoi in ogni PDF? Scrivi un numero intero, ad esempio 5."
        )
        await query.edit_message_text(prompt)
        return
    if not job_flow.has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    if output_choice == "zip":
        split_output_zip = True
        choice_label = "zip"
    elif output_choice == "files":
        split_output_zip = False
        choice_label = "pdf separati"
    else:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    try:
        job = await job_flow.enqueue_job(
            deps=deps,
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
    bot_runtime._record_split_output_choice(deps, user.id, split_output_zip)
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        bot_runtime._build_pending_action_queued_message(SupportedAction.PDF_SPLIT, job.id, choice_label)
    )


async def handle_rotate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    degrees = int((query.data or "").removeprefix("rotate:"))
    bot_runtime._record_callback_metric(deps, f"rotate:{degrees}")
    if not job_flow.has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    job = await job_flow.enqueue_job(
        deps=deps,
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
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    try:
        _, layout_choice, action_name = (query.data or "").split(":", 2)
        action = SupportedAction(action_name)
    except (TypeError, ValueError):
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    bot_runtime._record_callback_metric(deps, f"images_pdf_layout:{layout_choice}")
    if not bot_runtime._is_image_pdf_action(action):
        await query.edit_message_text("Questa opzione non è supportata per il PDF richiesto.")
        return
    if layout_choice == "a4":
        session.pending_action = bot_sessions._build_images_pdf_margin_pending_action(action)
        session.touch()
        deps.session_store.save(session)
        await query.edit_message_text(
            "Che bordi vuoi nell'impaginazione A4?", reply_markup=build_images_pdf_margin_keyboard(action.value)
        )
        return
    if layout_choice != "original":
        await query.edit_message_text("Scelta non valida.")
        return
    await bot_sessions._enqueue_image_pdf_job_from_callback(
        query=query,
        context=context,
        user_id=user.id,
        action=action,
        session=session,
        image_pdf_use_a4=False,
        image_pdf_margin_px=A4_MARGIN_NONE_PX,
    )


async def handle_images_pdf_margin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    try:
        _, margin_choice, action_name = (query.data or "").split(":", 2)
        action = SupportedAction(action_name)
    except (TypeError, ValueError):
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    bot_runtime._record_callback_metric(deps, f"images_pdf_margin:{margin_choice}")
    margin_map = {"wide": A4_MARGIN_WIDE_PX, "narrow": A4_MARGIN_NARROW_PX, "none": A4_MARGIN_NONE_PX}
    margin_px = margin_map.get(margin_choice)
    if margin_px is None:
        await query.edit_message_text("Scelta non valida.")
        return
    await bot_sessions._enqueue_image_pdf_job_from_callback(
        query=query,
        context=context,
        user_id=user.id,
        action=action,
        session=session,
        image_pdf_use_a4=True,
        image_pdf_margin_px=margin_px,
    )


async def handle_images_pdf_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    try:
        _, layout_choice, margin_choice, action_name = (query.data or "").split(":", 3)
        action = SupportedAction(action_name)
    except (TypeError, ValueError):
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    bot_runtime._record_callback_metric(deps, f"images_pdf_preset:{layout_choice}:{margin_choice}")
    if not bot_runtime._is_image_pdf_action(action) or layout_choice != "a4":
        await query.edit_message_text("Questa opzione non è supportata per il PDF richiesto.")
        return
    margin_map = {"wide": A4_MARGIN_WIDE_PX, "narrow": A4_MARGIN_NARROW_PX, "none": A4_MARGIN_NONE_PX}
    margin_px = margin_map.get(margin_choice)
    if margin_px is None:
        await query.edit_message_text("Scelta non valida.")
        return
    await bot_sessions._enqueue_image_pdf_job_from_callback(
        query=query,
        context=context,
        user_id=user.id,
        action=action,
        session=session,
        image_pdf_use_a4=True,
        image_pdf_margin_px=margin_px,
    )


async def handle_document_photo_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    query = update.callback_query
    await bot_runtime._safe_answer_callback(query)
    user = query.from_user
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await query.edit_message_text(UNAUTHORIZED_MESSAGE)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await query.edit_message_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    session = deps.session_store.get(user.id)
    if session is None or not session.files:
        await query.edit_message_text(SESSION_EMPTY_MESSAGE)
        return
    raw_mode = (query.data or "").removeprefix("document_photo_mode:")
    bot_runtime._record_callback_metric(deps, f"document_photo_mode:{raw_mode}")
    try:
        mode = DocumentPhotoMode(raw_mode)
    except ValueError:
        await query.edit_message_text(bot_runtime._invalid_callback_message())
        return
    if SupportedAction.DOCUMENT_PHOTO_FIX not in infer_supported_actions(session):
        await query.edit_message_text(
            "Questa scelta non è più compatibile con la sessione corrente. Inviami una foto del documento oppure usa /reset per ripartire."
        )
        return
    if not job_flow.has_capacity_for_new_job(user.id, deps):
        await query.edit_message_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
        return
    job = await job_flow.enqueue_job(
        deps=deps,
        user_id=user.id,
        chat_id=query.message.chat_id,
        reply_to_message_id=query.message.message_id,
        action=SupportedAction.DOCUMENT_PHOTO_FIX,
        session=session,
        document_photo_mode=mode,
    )
    deps.session_store.delete(user.id)
    await query.edit_message_text(
        f"{_document_photo_mode_label(mode)} selezionato. {bot_runtime._build_text_request_queued_message(SupportedAction.DOCUMENT_PHOTO_FIX, job.id, None)}"
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_runtime.logger.exception("Errore non gestito", exc_info=context.error)


async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps = bot_runtime._get_dependencies(context)
    bot_runtime._purge_expired_sessions(deps)
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    if not _is_authorized_for_deps(user.id if user else None, deps):
        await bot_runtime._handle_unauthorized_access_attempt(user, context, deps, message)
        return
    if bot_runtime._is_service_paused(deps) and (not _is_admin(user.id if user else None, deps.settings)):
        await message.reply_text(bot_runtime._build_service_unavailable_message())
        return
    await bot_runtime._maybe_notify_admins_about_new_user(user, context)
    text = (message.text or "").strip()
    if text == "Storico lavori":
        await bot_results.history_command(update, context)
        return
    if text == "Nuovo lavoro":
        await bot_sessions.reset_command(update, context)
        return
    if text == "Guida rapida":
        await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())
        return
    session = deps.session_store.get(user.id)
    if bot_runtime._is_latest_job_rerun_text(text) and (not (session is not None and session.files)):
        await bot_results._rerun_latest_user_job(deps=deps, user_id=user.id, message=message)
        return
    if session is not None and session.files:
        if session.pending_action is not None:
            handled = await bot_sessions._handle_pending_session_input(
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
                deps.session_store.record_flow_event(
                    user.id, session.created_at.isoformat(), "action_selected", text_request.action.value
                )
                session.pending_action = text_request.action.value
                session.touch()
                deps.session_store.save(session)
                if text_request.action == SupportedAction.PDF_SPLIT:
                    await message.reply_text(
                        _build_split_output_prompt(user.id, deps),
                        reply_markup=build_split_output_keyboard(
                            bot_runtime._get_stored_split_output_choice(deps, user.id, preset_only=True)
                        ),
                    )
                else:
                    await message.reply_text(
                        text_request.message or bot_runtime._build_pending_action_prompt(text_request.action)
                    )
                return
            action = text_request.action
            if action is None:
                await message.reply_text(
                    "Non ho capito abbastanza bene la richiesta. Prova a riformularla in modo più diretto."
                )
                return
            deps.session_store.record_flow_event(
                user.id, session.created_at.isoformat(), "action_selected", action.value
            )
            if not job_flow.has_capacity_for_new_job(user.id, deps):
                await message.reply_text(build_job_queue_limit_message(deps.settings.max_active_jobs_per_user))
                return
            if bot_runtime._is_image_pdf_action(action):
                session.pending_action = bot_sessions._build_images_pdf_layout_pending_action(action)
                session.touch()
                deps.session_store.save(session)
                await message.reply_text(
                    _build_image_pdf_layout_prompt(user.id, deps),
                    reply_markup=build_images_pdf_layout_keyboard(
                        action.value,
                        preset_layout=bot_runtime._get_stored_image_pdf_layout(deps, user.id, preset_only=True),
                        preset_margin_px=bot_runtime._get_stored_image_pdf_margin(deps, user.id, preset_only=True),
                    ),
                )
                return
            if action == SupportedAction.DOCUMENT_PHOTO_FIX and text_request.document_photo_mode is None:
                session.pending_action = bot_runtime._PENDING_DOCUMENT_PHOTO_MODE
                session.touch()
                deps.session_store.save(session)
                await message.reply_text(
                    _build_document_photo_mode_prompt(), reply_markup=build_document_photo_mode_keyboard()
                )
                return
            compression_preset = text_request.compression_preset
            if action == SupportedAction.PDF_COMPRESS:
                compression_preset = bot_runtime._resolve_compression_preset_for_job(deps, user.id, compression_preset)
            job = await job_flow.enqueue_job(
                deps=deps,
                user_id=user.id,
                chat_id=message.chat_id,
                reply_to_message_id=message.message_id,
                action=action,
                session=session,
                compression_preset=compression_preset,
                rotate_degrees=text_request.rotate_degrees,
                page_selection=text_request.page_selection,
                watermark_text=text_request.watermark_text,
                split_output_zip=text_request.split_output_zip if text_request.split_output_zip is not None else True,
                document_photo_mode=text_request.document_photo_mode or DocumentPhotoMode.READABLE,
            )
            if action == SupportedAction.PDF_COMPRESS and compression_preset is not None:
                bot_runtime._record_user_choice(
                    deps, user.id, bot_runtime._COMPRESSION_PRESET_KEY, compression_preset.value
                )
            if action == SupportedAction.PDF_SPLIT:
                bot_runtime._record_split_output_choice(
                    deps, user.id, text_request.split_output_zip if text_request.split_output_zip is not None else True
                )
            deps.session_store.delete(user.id)
            if action == SupportedAction.PDF_SPLIT:
                await message.reply_text(
                    bot_runtime._build_pending_action_queued_message(
                        action, job.id, "zip" if text_request.split_output_zip else "pdf separati"
                    )
                )
            elif text_request.page_selection or text_request.watermark_text:
                raw_value = text_request.page_selection or text_request.watermark_text or ""
                await message.reply_text(
                    bot_runtime._build_pending_action_queued_message(action, job.id, str(raw_value))
                )
            elif text_request.rotate_degrees is not None:
                await message.reply_text(
                    f"Rotazione manuale presa in carico di {text_request.rotate_degrees} gradi. Job #{job.id} in coda.\nTi invio il PDF appena è pronto."
                )
            else:
                await message.reply_text(
                    bot_runtime._build_text_request_queued_message(action, job.id, compression_preset)
                )
            return
    quick_action_guidance = _build_quick_action_guidance(session, text)
    if quick_action_guidance is not None:
        await message.reply_text(quick_action_guidance, reply_markup=build_main_menu_keyboard())
        return
    if bot_runtime._mentions_context_reference(text):
        await message.reply_text(
            bot_runtime._build_missing_context_reference_message(deps, user.id), reply_markup=build_main_menu_keyboard()
        )
        return
    await message.reply_text(
        "Per iniziare, inviami immagini, PDF o un file Excel. Se vuoi una guida rapida, usa /help oppure il menu qui sotto.",
        reply_markup=build_main_menu_keyboard(),
    )


async def _handle_start_payload(
    payload: str, deps: bot_runtime.BotDependencies, user_id: int, message: Message, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if payload == "help":
        await message.reply_text(HELP_MESSAGE, reply_markup=build_main_menu_keyboard())
        return True
    if payload in {"privacy", "dati", "data"}:
        await message.reply_text(_build_policy_message(deps), reply_markup=build_delete_data_request_keyboard())
        return True
    if payload == "history":
        jobs = deps.session_store.list_user_jobs(user_id, limit=5)
        if not jobs:
            await message.reply_text(
                "Non hai ancora uno storico lavori. Inviami immagini, PDF o un file Excel e terrò traccia degli ultimi job qui.",
                reply_markup=build_main_menu_keyboard(),
            )
        else:
            await message.reply_text(
                bot_results._build_user_history_summary(jobs),
                reply_markup=build_history_keyboard([job.id for job in jobs]),
            )
        return True
    if payload == "status":
        session = deps.session_store.get(user_id)
        if session is None or not session.files:
            await message.reply_text(SESSION_EMPTY_MESSAGE, reply_markup=build_main_menu_keyboard())
        else:
            session_text, session_keyboard = bot_runtime._build_session_reply(session)
            await message.reply_text(session_text, reply_markup=session_keyboard)
        return True
    return False


def _build_compression_prompt(user_id: int, deps: bot_runtime.BotDependencies) -> str:
    saved_preset = bot_runtime._get_stored_compression_preset(deps, user_id, preset_only=True)
    saved_preference = bot_runtime._get_stored_compression_preset(deps, user_id)
    if saved_preset:
        saved_note = f"\nPreset leggero pronto: {saved_preset}."
    elif saved_preference:
        saved_note = f"\nUltima scelta rapida salvata: {saved_preference}."
    else:
        saved_note = ""
    return f"Hai scelto la compressione PDF. Seleziona il livello.\nLeggera preserva di più il file; Media e Forte cercano una riduzione più evidente.{saved_note}"


def _build_split_output_prompt(user_id: int, deps: bot_runtime.BotDependencies) -> str:
    saved_preset = bot_runtime._get_stored_split_output_choice(deps, user_id, preset_only=True)
    saved_preference = bot_runtime._get_stored_split_output_choice(deps, user_id)
    if saved_preset == "zip":
        saved_note = "\nPreset leggero pronto: ZIP unico."
    elif saved_preset == "files":
        saved_note = "\nPreset leggero pronto: PDF separati."
    elif saved_preference == "zip":
        saved_note = "\nUltima scelta rapida salvata: ZIP unico."
    elif saved_preference == "files":
        saved_note = "\nUltima scelta rapida salvata: PDF separati."
    else:
        saved_note = ""
    return (
        "Come vuoi dividere il PDF? Puoi creare un file per pagina in ZIP o come allegati separati, "
        "gruppi personalizzati oppure blocchi da N pagine."
        f"{saved_note}"
    )


def _build_document_photo_mode_prompt() -> str:
    return "Come vuoi sistemare la foto del documento?\n- Più leggibile: migliora contrasto e pulizia generale.\n- Mantieni colore: conserva il colore del foglio.\n- Bianco/nero pulito: crea una scansione ad alto contrasto."


def _document_photo_mode_label(mode: DocumentPhotoMode) -> str:
    if mode == DocumentPhotoMode.COLOR:
        return "Mantieni colore"
    if mode == DocumentPhotoMode.BW:
        return "Bianco/nero pulito"
    return "Più leggibile"


def _build_policy_message(deps: bot_runtime.BotDependencies) -> str:
    settings = deps.settings
    return (
        "Policy sintetica DocMolder\n\n"
        "Uso supportato:\n"
        "- invia PDF, immagini o scansioni nella chat privata con il bot\n"
        "- ogni richiesta deve essere una trasformazione documentale chiara e circoscritta\n\n"
        "Dati e retention:\n"
        "- i file caricati servono solo per creare il risultato richiesto\n"
        f"- le directory job temporanee vengono pulite dopo circa {settings.stale_job_retention_hours} ore\n"
        f"- lo storico job live viene potato dopo {settings.job_history_retention_days} giorni\n"
        "- il database conserva metadati tecnici dei job, preferenze minime, audit admin e metriche operative\n"
        "- il contenuto dei documenti non viene scritto nei log e non va inserito in issue, test o report\n\n"
        "Cancellazione:\n"
        "- /reset inizia un nuovo lavoro senza toccare preferenze, preset o storico\n"
        "- da /start privacy puoi ripristinare le preferenze o cancellare tutti i dati live con conferma inline\n"
        "- i backup tecnici già creati non vengono riscritti e scadono con la loro retention breve\n\n"
        "Preset:\n"
        "- salvo solo impostazioni operative ripetute, come compressione, layout immagini PDF e output split\n"
        "- non salvo contenuti dei documenti o nomi file dentro i preset\n\n"
        "Limiti operativi:\n"
        f"- file massimo: {settings.max_file_size_mb} MB\n"
        f"- file per sessione: {settings.max_session_files}\n"
        f"- job attivi per utente: {settings.max_active_jobs_per_user}\n"
        f"- upload rapido: {settings.upload_burst_limit} file in {settings.upload_burst_window_seconds} secondi\n\n"
        f"Dettagli pubblici: {PUBLIC_PRIVACY_URL}\n\n"
        "Accesso:\n"
        "- se il bot è ristretto, la richiesta accesso parte dal primo messaggio inviato al bot\n"
        "- in manutenzione i nuovi job utente sono sospesi, mentre gli admin possono usare /admin"
    )


def _build_image_pdf_layout_prompt(user_id: int, deps: bot_runtime.BotDependencies) -> str:
    saved_layout = bot_runtime._get_stored_image_pdf_layout(deps, user_id, preset_only=True)
    saved_margin = bot_runtime._get_stored_image_pdf_margin(deps, user_id, preset_only=True)
    saved_note_prefix = "Preset leggero pronto"
    if saved_layout is None:
        saved_layout = bot_runtime._get_stored_image_pdf_layout(deps, user_id)
        saved_margin = bot_runtime._get_stored_image_pdf_margin(deps, user_id)
        saved_note_prefix = "Ultima scelta rapida salvata"
    saved_note = ""
    if saved_layout == "original":
        saved_note = f"\n{saved_note_prefix}: formato originale."
    elif saved_layout == "a4":
        saved_note = f"\n{saved_note_prefix}: A4"
        if saved_margin == str(A4_MARGIN_WIDE_PX):
            saved_note += " con bordi larghi."
        elif saved_margin == str(A4_MARGIN_NONE_PX):
            saved_note += " senza bordi."
        else:
            saved_note += " con bordi stretti."
    return f"Vuoi che impagini il PDF in formato A4?{saved_note}"
