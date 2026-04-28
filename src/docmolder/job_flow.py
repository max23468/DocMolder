from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from telegram.ext import Application

from docmolder.models import CompressionPreset, DocumentPhotoMode, JobPayload, JobRecord, SupportedAction, UserSession
from docmolder.processing import A4_MARGIN_NARROW_PX, DocumentProcessor, ProcessingResult, ProcessingUserError
from docmolder.action_catalog import build_output_stem, build_session_file, infer_session_analysis
from docmolder.session_store import SessionStore


class JobFlowDependencies(Protocol):
    session_store: SessionStore
    job_queue: asyncio.Queue[int]
    processor: DocumentProcessor


async def enqueue_job(
    *,
    deps: JobFlowDependencies,
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
    session_analysis = infer_session_analysis(session)
    if action not in session_analysis.supported_actions:
        raise ProcessingUserError("L'azione scelta non è più disponibile per la sessione corrente.")

    payload = JobPayload.from_session(
        session,
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
    job = deps.session_store.create_job(
        user_id=user_id,
        chat_id=chat_id,
        reply_to_message_id=reply_to_message_id,
        action=action.value,
        payload_json=payload.to_json(),
    )
    await deps.job_queue.put(job.id)
    return job


async def enqueue_job_from_existing_payload(
    *,
    deps: JobFlowDependencies,
    source_job: JobRecord,
    reply_to_message_id: int | None,
    auto_rotate_pdf: bool | None = None,
) -> JobRecord:
    payload = JobPayload.from_json(source_job.payload_json)
    if auto_rotate_pdf is not None:
        payload.auto_rotate_pdf = auto_rotate_pdf
    job = deps.session_store.create_job(
        user_id=source_job.user_id,
        chat_id=source_job.chat_id,
        reply_to_message_id=reply_to_message_id,
        action=source_job.action,
        payload_json=payload.to_json(),
        rerun_of_job_id=source_job.id,
    )
    await deps.job_queue.put(job.id)
    return job


async def run_job_payload(
    *,
    application: Application,
    processor: DocumentProcessor,
    job: JobRecord,
    job_dir: Path,
    download_session_files: Callable[[Application, UserSession, Path], Awaitable[list[Path]]],
) -> ProcessingResult:
    payload = JobPayload.from_json(job.payload_json)
    session = UserSession(
        user_id=job.user_id,
        files=[
            build_session_file(
                file_id=item.telegram_file_id,
                file_name=item.file_name,
                kind=item.kind,
            )
            for item in payload.files
        ],
    )

    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    downloaded_paths = await download_session_files(application, session, input_dir)

    return await asyncio.to_thread(
        processor.process,
        SupportedAction(job.action),
        downloaded_paths,
        build_output_stem(SupportedAction(job.action), session.files),
        payload.compression_preset,
        payload.rotate_degrees,
        payload.page_selection,
        payload.watermark_text,
        payload.auto_rotate_pdf,
        payload.image_pdf_use_a4,
        payload.image_pdf_margin_px if payload.image_pdf_margin_px is not None else A4_MARGIN_NARROW_PX,
        payload.split_output_zip,
        payload.document_photo_mode,
    )
