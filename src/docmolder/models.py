from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import json
from typing import Literal, TypeAlias
from typing import TypedDict


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


SupportedActionValue: TypeAlias = Literal[
    "images_to_pdf",
    "images_to_pdf_crop",
    "images_to_pdf_grayscale",
    "images_to_pdf_crop_grayscale",
    "pdf_grayscale",
    "pdf_compress",
    "pdf_merge",
    "pdf_extract_pages",
    "pdf_reorder_pages",
    "pdf_delete_pages",
    "pdf_rotate",
    "pdf_watermark",
    "auto_orient",
]

PendingActionValue: TypeAlias = SupportedActionValue | Literal[
    "images_pdf_layout:images_to_pdf",
    "images_pdf_layout:images_to_pdf_crop",
    "images_pdf_layout:images_to_pdf_grayscale",
    "images_pdf_layout:images_to_pdf_crop_grayscale",
    "images_pdf_margin:images_to_pdf",
    "images_pdf_margin:images_to_pdf_crop",
    "images_pdf_margin:images_to_pdf_grayscale",
    "images_pdf_margin:images_to_pdf_crop_grayscale",
]


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
    pending_action: PendingActionValue | None = None
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
    action: SupportedActionValue
    payload_json: str
    status: JobStatus
    created_at: datetime
    rerun_of_job_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_message: str | None = None
    error_message: str | None = None
    processing_mode: str | None = None
    input_bytes: int | None = None
    output_bytes: int | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class JobPayloadFile:
    telegram_file_id: str
    file_name: str
    kind: FileKind


class JobPayloadFileData(TypedDict):
    telegram_file_id: str
    file_name: str
    kind: str


class JobPayloadData(TypedDict, total=False):
    files: list[JobPayloadFileData]
    compression_preset: str | None
    rotate_degrees: int | None
    page_selection: str | None
    watermark_text: str | None
    auto_rotate_pdf: bool
    image_pdf_use_a4: bool
    image_pdf_margin_px: int | None


@dataclass(slots=True)
class JobPayload:
    files: list[JobPayloadFile]
    compression_preset: CompressionPreset | None = None
    rotate_degrees: int | None = None
    page_selection: str | None = None
    watermark_text: str | None = None
    auto_rotate_pdf: bool = True
    image_pdf_use_a4: bool = True
    image_pdf_margin_px: int | None = None

    @classmethod
    def from_json(cls, payload_json: str) -> "JobPayload":
        raw_payload = json.loads(payload_json)
        if not isinstance(raw_payload, dict):
            raise TypeError("Il payload del job deve essere un oggetto JSON.")
        return cls.from_dict(raw_payload)

    @classmethod
    def from_dict(cls, raw_payload: JobPayloadData) -> "JobPayload":
        raw_files = raw_payload.get("files", [])
        files = [
            JobPayloadFile(
                telegram_file_id=str(item["telegram_file_id"]),
                file_name=str(item["file_name"]),
                kind=FileKind(str(item["kind"])),
            )
            for item in raw_files
            if isinstance(item, dict)
        ]
        compression_raw = raw_payload.get("compression_preset")
        return cls(
            files=files,
            compression_preset=CompressionPreset(str(compression_raw)) if compression_raw else None,
            rotate_degrees=int(raw_payload["rotate_degrees"]) if raw_payload.get("rotate_degrees") is not None else None,
            page_selection=str(raw_payload["page_selection"]) if raw_payload.get("page_selection") is not None else None,
            watermark_text=str(raw_payload["watermark_text"]) if raw_payload.get("watermark_text") is not None else None,
            auto_rotate_pdf=bool(raw_payload.get("auto_rotate_pdf", True)),
            image_pdf_use_a4=bool(raw_payload.get("image_pdf_use_a4", True)),
            image_pdf_margin_px=(
                int(raw_payload["image_pdf_margin_px"]) if raw_payload.get("image_pdf_margin_px") is not None else None
            ),
        )

    @classmethod
    def from_session(
        cls,
        session: UserSession,
        *,
        compression_preset: CompressionPreset | None = None,
        rotate_degrees: int | None = None,
        page_selection: str | None = None,
        watermark_text: str | None = None,
        auto_rotate_pdf: bool = True,
        image_pdf_use_a4: bool = True,
        image_pdf_margin_px: int | None = None,
    ) -> "JobPayload":
        return cls(
            files=[
                JobPayloadFile(
                    telegram_file_id=item.telegram_file_id,
                    file_name=item.file_name,
                    kind=item.kind,
                )
                for item in session.files
            ],
            compression_preset=compression_preset,
            rotate_degrees=rotate_degrees,
            page_selection=page_selection,
            watermark_text=watermark_text,
            auto_rotate_pdf=auto_rotate_pdf,
            image_pdf_use_a4=image_pdf_use_a4,
            image_pdf_margin_px=image_pdf_margin_px,
        )

    def to_dict(self) -> JobPayloadData:
        return {
            "files": [
                {
                    "telegram_file_id": item.telegram_file_id,
                    "file_name": item.file_name,
                    "kind": item.kind.value,
                }
                for item in self.files
            ],
            "compression_preset": self.compression_preset.value if self.compression_preset else None,
            "rotate_degrees": self.rotate_degrees,
            "page_selection": self.page_selection,
            "watermark_text": self.watermark_text,
            "auto_rotate_pdf": self.auto_rotate_pdf,
            "image_pdf_use_a4": self.image_pdf_use_a4,
            "image_pdf_margin_px": self.image_pdf_margin_px,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass(slots=True)
class AdminUserStat:
    user_id: int
    label: str
    completed_actions: int


@dataclass(slots=True)
class AdminActionStat:
    action: SupportedActionValue
    total: int


@dataclass(slots=True)
class AdminStats:
    known_users_total: int
    known_users_last_24h: int
    known_users_last_7d: int
    completed_actions_total: int
    completed_actions_last_24h: int
    completed_actions_last_7d: int
    active_sessions: int
    images_to_pdf_total: int
    pdf_compress_total: int
    pdf_grayscale_total: int
    pdf_merge_total: int
    pdf_extract_pages_total: int
    pdf_reorder_pages_total: int
    pdf_delete_pages_total: int
    pdf_rotate_total: int
    pdf_watermark_total: int
    auto_orient_total: int
    jobs_queued: int
    jobs_running: int
    jobs_failed: int
    jobs_succeeded: int
    raster_results_total: int
    avg_duration_ms: int
    avg_input_bytes: int
    avg_output_bytes: int
