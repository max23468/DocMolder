from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class SessionStatus(StrEnum):
    COLLECTING = "collecting"
    READY = "ready"


class SupportedAction(StrEnum):
    IMAGES_TO_PDF = "images_to_pdf"
    IMAGES_TO_PDF_CROP = "images_to_pdf_crop"
    IMAGES_TO_PDF_GRAYSCALE = "images_to_pdf_grayscale"
    IMAGES_TO_PDF_CROP_GRAYSCALE = "images_to_pdf_crop_grayscale"
    PDF_GRAYSCALE = "pdf_grayscale"
    PDF_COMPRESS = "pdf_compress"
    PDF_MERGE = "pdf_merge"
    PDF_EXTRACT_PAGES = "pdf_extract_pages"
    PDF_REORDER_PAGES = "pdf_reorder_pages"
    PDF_DELETE_PAGES = "pdf_delete_pages"
    PDF_ROTATE = "pdf_rotate"
    PDF_WATERMARK = "pdf_watermark"
    AUTO_ORIENT = "auto_orient"


class CompressionPreset(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    STRONG = "strong"


class FileKind(StrEnum):
    IMAGE = "image"
    PDF = "pdf"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class SessionFile:
    telegram_file_id: str
    file_name: str
    kind: FileKind
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class UserSession:
    user_id: int
    files: list[SessionFile] = field(default_factory=list)
    status: SessionStatus = SessionStatus.COLLECTING
    pending_action: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def is_expired(self, ttl_minutes: int) -> bool:
        return datetime.now(timezone.utc) > self.updated_at + timedelta(minutes=ttl_minutes)


@dataclass(slots=True)
class JobRecord:
    id: int
    user_id: int
    chat_id: int
    reply_to_message_id: int | None
    action: str
    payload_json: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_message: str | None = None
    error_message: str | None = None
    processing_mode: str | None = None
    input_bytes: int | None = None
    output_bytes: int | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class AdminUserStat:
    user_id: int
    label: str
    completed_actions: int


@dataclass(slots=True)
class AdminActionStat:
    action: str
    total: int
