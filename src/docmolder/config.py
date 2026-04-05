from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_token: str = Field(alias="DOCMOLDER_TELEGRAM_TOKEN")
    allowed_user_ids: list[int] = Field(default_factory=list, alias="DOCMOLDER_ALLOWED_USER_IDS")
    admin_user_ids: list[int] = Field(default_factory=list, alias="DOCMOLDER_ADMIN_USER_IDS")
    default_language: str = Field(default="it", alias="DOCMOLDER_DEFAULT_LANGUAGE")
    session_ttl_minutes: int = Field(default=30, alias="DOCMOLDER_SESSION_TTL_MINUTES")
    max_session_files: int = Field(default=20, alias="DOCMOLDER_MAX_SESSION_FILES")
    max_file_size_mb: int = Field(default=20, alias="DOCMOLDER_MAX_FILE_SIZE_MB")
    cleanup_interval_minutes: int = Field(default=30, alias="DOCMOLDER_CLEANUP_INTERVAL_MINUTES")
    stale_job_retention_hours: int = Field(default=6, alias="DOCMOLDER_STALE_JOB_RETENTION_HOURS")
    runtime_dir: Path = Field(default=Path("./data/runtime"), alias="DOCMOLDER_RUNTIME_DIR")
    database_path: Path = Field(default=Path("./data/runtime/docmolder.db"), alias="DOCMOLDER_DATABASE_PATH")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, value: object) -> list[int]:
        return cls._parse_id_list(value, "DOCMOLDER_ALLOWED_USER_IDS")

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def parse_admin_user_ids(cls, value: object) -> list[int]:
        return cls._parse_id_list(value, "DOCMOLDER_ADMIN_USER_IDS")

    @classmethod
    def _parse_id_list(cls, value: object, field_name: str) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        raise TypeError(f"{field_name} deve essere una lista o una stringa separata da virgole.")

    def ensure_runtime_dirs(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        (self.runtime_dir / "sessions").mkdir(parents=True, exist_ok=True)
        (self.runtime_dir / "jobs").mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_dirs()
    return settings
