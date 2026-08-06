from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from docmolder.bot_admin import admin_command, handle_access_review_callback, handle_admin_callback
from docmolder.bot_jobs import _post_init, _post_shutdown
from docmolder.bot_menu import (
    error_handler,
    handle_action_callback,
    handle_compression_callback,
    handle_document_photo_mode_callback,
    handle_images_pdf_layout_callback,
    handle_images_pdf_margin_callback,
    handle_images_pdf_preset_callback,
    handle_menu_text,
    handle_rotate_callback,
    handle_split_output_callback,
    help_command,
    start_command,
)
from docmolder.bot_results import handle_history_callback, handle_result_action_callback, history_command
from docmolder.bot_runtime import BotDependencies, _configure_logging, _private_chat_only
from docmolder.bot_sessions import (
    handle_delete_data_callback,
    handle_document,
    handle_photo,
    reset_command,
    status_command,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.sqlite_session_store import SQLiteSessionStore


def build_application(settings: Settings) -> Application:
    """Compone dipendenze e dispatch Telegram senza contenere logica di flusso."""
    _configure_logging()
    deps = BotDependencies(
        settings=settings,
        session_store=SQLiteSessionStore(settings.database_path),
        processor=DocumentProcessor(
            runtime_dir=settings.runtime_dir,
            ghostscript_timeout_seconds=settings.ghostscript_timeout_seconds,
            image_pdf_max_source_side_px=settings.image_pdf_max_source_side_px,
            libreoffice_timeout_seconds=settings.libreoffice_timeout_seconds,
        ),
    )
    application = (
        Application.builder().token(settings.telegram_token).post_init(_post_init).post_shutdown(_post_shutdown).build()
    )
    application.bot_data["deps"] = deps

    application.add_handler(TypeHandler(Update, _private_chat_only), group=-1)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(handle_access_review_callback, pattern=r"^access:"))
    application.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin:"))
    application.add_handler(CallbackQueryHandler(handle_delete_data_callback, pattern=r"^delete_data:"))
    application.add_handler(CallbackQueryHandler(handle_history_callback, pattern=r"^history:"))
    application.add_handler(CallbackQueryHandler(handle_rotate_callback, pattern=r"^rotate:"))
    application.add_handler(CallbackQueryHandler(handle_result_action_callback, pattern=r"^result:"))
    application.add_handler(CallbackQueryHandler(handle_compression_callback, pattern=r"^compress:"))
    application.add_handler(CallbackQueryHandler(handle_split_output_callback, pattern=r"^split_output:"))
    application.add_handler(CallbackQueryHandler(handle_document_photo_mode_callback, pattern=r"^document_photo_mode:"))
    application.add_handler(CallbackQueryHandler(handle_images_pdf_preset_callback, pattern=r"^images_pdf_preset:"))
    application.add_handler(CallbackQueryHandler(handle_images_pdf_margin_callback, pattern=r"^images_pdf_margin:"))
    application.add_handler(CallbackQueryHandler(handle_images_pdf_layout_callback, pattern=r"^images_pdf_layout:"))
    application.add_handler(CallbackQueryHandler(handle_action_callback, pattern=r"^action:"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_text))
    application.add_error_handler(error_handler)
    return application
