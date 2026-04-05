from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class SessionStatus(StrEnum):
    COLLECTING = "collecting"
    READY = "ready"


class SupportedAction(StrEnum):
    IMAGES_TO_PDF = "images_to_pdf"
    PDF_GRAYSCALE = "pdf_grayscale"
    PDF_COMPRESS = "pdf_compress"
    PDF_MERGE = "pdf_merge"
    PDF_ROTATE = "pdf_rotate"
    AUTO_ORIENT = "auto_orient"


class CompressionPreset(StrEnum):
    LIGHT = "light"
    MEDIUM = "medium"
    STRONG = "strong"


class FileKind(StrEnum):
    IMAGE = "image"
    PDF = "pdf"


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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def is_expired(self, ttl_minutes: int) -> bool:
        return datetime.now(timezone.utc) > self.updated_at + timedelta(minutes=ttl_minutes)
