from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from time import perf_counter
from telegram.ext import Application, ContextTypes
from docmolder.job_flow import (
    enqueue_job as enqueue_job_flow,
    enqueue_job_from_existing_payload as enqueue_job_from_existing_payload_flow,
    run_job_payload as run_job_payload_flow,
)
from docmolder.logging_utils import log_event
from docmolder.messages import GENERIC_ERROR_MESSAGE
from docmolder.models import CompressionPreset, DocumentPhotoMode, FileKind, JobRecord, SupportedAction, UserSession
from docmolder.processing_models import A4_MARGIN_NARROW_PX, ProcessingResult, ProcessingUserError
from docmolder.action_catalog import sanitize_filename
import docmolder.admin_reporting as admin_reporting
import docmolder.bot_results as bot_results
import docmolder.bot_runtime as bot_runtime
import docmolder.bot_sessions as bot_sessions


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
    document_photo_mode: DocumentPhotoMode = DocumentPhotoMode.READABLE,
) -> JobRecord:
    deps = bot_runtime._get_dependencies(context)
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
        document_photo_mode=document_photo_mode,
    )


async def _enqueue_job_from_existing_payload(
    context: ContextTypes.DEFAULT_TYPE,
    source_job: JobRecord,
    reply_to_message_id: int | None,
    *,
    auto_rotate_pdf: bool | None = None,
) -> JobRecord:
    deps = bot_runtime._get_dependencies(context)
    return await enqueue_job_from_existing_payload_flow(
        deps=deps, source_job=source_job, reply_to_message_id=reply_to_message_id, auto_rotate_pdf=auto_rotate_pdf
    )


async def _run_job_payload(application: Application, job: JobRecord, job_dir: Path) -> ProcessingResult:
    deps: bot_runtime.BotDependencies = application.bot_data["deps"]
    return await run_job_payload_flow(
        application=application,
        processor=deps.processor,
        job=job,
        job_dir=job_dir,
        download_session_files=_download_session_files,
    )


async def _post_init(application: Application) -> None:
    deps: bot_runtime.BotDependencies = application.bot_data["deps"]
    _run_cleanup_cycle(deps)
    await bot_runtime._sync_telegram_branding(application, deps.settings, deps.session_store)
    requeued_jobs = deps.session_store.requeue_incomplete_jobs()
    for job in requeued_jobs:
        await deps.job_queue.put(job.id)
    if requeued_jobs:
        bot_runtime.logger.info("Ripresi %s job incompleti dalla coda persistente.", len(requeued_jobs))
        log_event(bot_runtime.logger, logging.INFO, "jobs_requeued_on_startup", count=len(requeued_jobs))
    deps.job_worker_task = asyncio.create_task(_job_worker(application))
    deps.cleanup_task = asyncio.create_task(_cleanup_worker(deps))
    deps.admin_report_task = asyncio.create_task(admin_reporting._admin_report_worker(application))


async def _post_shutdown(application: Application) -> None:
    deps: bot_runtime.BotDependencies = application.bot_data["deps"]
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


def _has_capacity_for_new_job(user_id: int, deps: bot_runtime.BotDependencies) -> bool:
    return deps.session_store.count_active_jobs_for_user(user_id) < deps.settings.max_active_jobs_per_user


async def _job_worker(application: Application) -> None:
    deps: bot_runtime.BotDependencies = application.bot_data["deps"]
    while True:
        job_id = await deps.job_queue.get()
        try:
            await _process_job(application, job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            bot_runtime.logger.exception("Errore non gestito nel worker del job %s", job_id)
        finally:
            deps.job_queue.task_done()


async def _cleanup_worker(deps: bot_runtime.BotDependencies) -> None:
    interval_seconds = max(60, deps.settings.cleanup_interval_minutes * 60)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            _run_cleanup_cycle(deps)
        except asyncio.CancelledError:
            raise
        except Exception:
            bot_runtime.logger.exception("Errore durante il cleanup schedulato.")


def _run_cleanup_cycle(deps: bot_runtime.BotDependencies) -> None:
    removed_dirs = deps.processor.cleanup_stale_job_dirs(deps.settings.stale_job_retention_hours)
    if removed_dirs:
        bot_runtime.logger.info("Cleanup schedulato: rimosse %s cartelle temporanee residue.", removed_dirs)
    log_event(bot_runtime.logger, logging.INFO, "cleanup_cycle_complete", removed_dirs=removed_dirs)


async def _process_job(application: Application, job_id: int) -> None:
    deps: bot_runtime.BotDependencies = application.bot_data["deps"]
    job = deps.session_store.get_job(job_id)
    if job is None:
        return
    deps.session_store.mark_job_running(job_id)
    job = deps.session_store.get_job(job_id)
    if job is None:
        return
    log_event(bot_runtime.logger, logging.INFO, "job_started", job_id=job.id, user_id=job.user_id, action=job.action)
    await bot_runtime._safe_send_message(
        application.bot,
        chat_id=job.chat_id,
        text=bot_runtime._build_processing_started_message(SupportedAction(job.action), job.id),
        reply_to_message_id=job.reply_to_message_id,
        deps=deps,
    )
    job_dir = deps.processor.create_job_dir(job.user_id)
    started_monotonic = perf_counter()
    try:
        try:
            result = await _run_job_payload(application, job, job_dir)
        except ProcessingUserError as exc:
            if deps.session_store.get_job(job.id) is None:
                log_event(
                    bot_runtime.logger,
                    logging.INFO,
                    "job_discarded_after_user_data_deleted",
                    job_id=job.id,
                    action=job.action,
                )
                return
            deps.session_store.mark_job_failed(job.id, str(exc))
            log_event(
                bot_runtime.logger,
                logging.WARNING,
                "job_failed",
                job_id=job.id,
                user_id=job.user_id,
                action=job.action,
                error_type=type(exc).__name__,
            )
            await bot_runtime._safe_send_message(
                application.bot,
                chat_id=job.chat_id,
                text=f"Job #{job.id} non riuscito.\n{exc}",
                reply_to_message_id=job.reply_to_message_id,
                deps=deps,
            )
            return
        except Exception:
            if deps.session_store.get_job(job.id) is None:
                log_event(
                    bot_runtime.logger,
                    logging.INFO,
                    "job_discarded_after_user_data_deleted",
                    job_id=job.id,
                    action=job.action,
                )
                return
            bot_runtime.logger.exception("Errore durante il job %s", job.id)
            deps.session_store.mark_job_failed(job.id, GENERIC_ERROR_MESSAGE)
            log_event(
                bot_runtime.logger,
                logging.ERROR,
                "job_failed",
                job_id=job.id,
                user_id=job.user_id,
                action=job.action,
                error_type="unexpected",
            )
            await bot_runtime._safe_send_message(
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
        if deps.session_store.get_job(job.id) is None:
            log_event(
                bot_runtime.logger,
                logging.INFO,
                "job_discarded_after_user_data_deleted",
                job_id=job.id,
                action=job.action,
            )
            return
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
            bot_runtime.logger,
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
        if (
            not result.additional_outputs
            and result_message is not None
            and (getattr(result_message, "document", None) is not None)
        ):
            result_document = result_message.document
            result_file_id = getattr(result_document, "file_id", None)
            result_file_name = getattr(result_document, "file_name", None)
            if (
                isinstance(result_file_id, str)
                and (result_file_name is None or isinstance(result_file_name, str))
                and (bot_sessions._infer_document_kind(result_document) == FileKind.PDF)
            ):
                deps.session_store.save(
                    bot_results._build_result_pdf_session(job.user_id, result_file_id, result_file_name)
                )
    finally:
        deps.processor.cleanup_job_dir(job_dir)


async def _download_session_files(application: Application, session: UserSession, input_dir: Path) -> list[Path]:
    deps: bot_runtime.BotDependencies = application.bot_data["deps"]
    max_file_bytes = deps.settings.max_file_size_mb * 1024 * 1024
    max_job_bytes = max_file_bytes * min(deps.settings.max_session_files, 5)
    downloaded_bytes = 0
    downloaded_paths: list[Path] = []
    for index, session_file in enumerate(session.files, start=1):
        telegram_file = await application.bot.get_file(session_file.telegram_file_id)
        file_name = sanitize_filename(session_file.file_name)
        target_path = input_dir / f"{index:02d}_{file_name}"
        await telegram_file.download_to_drive(custom_path=str(target_path))
        file_bytes = target_path.stat().st_size
        downloaded_bytes += file_bytes
        if file_bytes > max_file_bytes or downloaded_bytes > max_job_bytes:
            target_path.unlink(missing_ok=True)
            raise ProcessingUserError(
                f"I file scaricati superano il budget del job. Limite: {deps.settings.max_file_size_mb} MB per file e {max_job_bytes // (1024 * 1024)} MB totali."
            )
        downloaded_paths.append(target_path)
    return downloaded_paths


async def _send_result(
    bot,
    chat_id: int,
    reply_to_message_id: int | None,
    result: ProcessingResult,
    *,
    deps: bot_runtime.BotDependencies | None = None,
    source_action: SupportedAction | None = None,
    source_job_id: int | None = None,
):
    first_message = None
    with result.output_path.open("rb") as payload:
        first_message = await bot_runtime._telegram_api_call(
            "sendDocument",
            bot.send_document,
            _deps=deps,
            chat_id=chat_id,
            document=payload,
            filename=result.output_name,
            caption=bot_results._build_result_delivery_message(result, source_action),
            reply_to_message_id=reply_to_message_id,
            reply_markup=bot_results._build_result_followup_keyboard(result, source_action, source_job_id),
        )
    for output in result.additional_outputs:
        with output.path.open("rb") as payload:
            await bot_runtime._telegram_api_call(
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
