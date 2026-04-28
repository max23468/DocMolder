from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    telegram_token: str = Field(alias="DOCMOLDER_TELEGRAM_TOKEN")
    allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list, alias="DOCMOLDER_ALLOWED_USER_IDS")
    admin_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list, alias="DOCMOLDER_ADMIN_USER_IDS")
    default_language: str = Field(default="it", alias="DOCMOLDER_DEFAULT_LANGUAGE")
    session_ttl_minutes: int = Field(default=30, alias="DOCMOLDER_SESSION_TTL_MINUTES")
    max_session_files: int = Field(default=20, alias="DOCMOLDER_MAX_SESSION_FILES")
    max_file_size_mb: int = Field(default=20, alias="DOCMOLDER_MAX_FILE_SIZE_MB")
    upload_burst_limit: int = Field(default=8, alias="DOCMOLDER_UPLOAD_BURST_LIMIT")
    upload_burst_window_seconds: int = Field(default=30, alias="DOCMOLDER_UPLOAD_BURST_WINDOW_SECONDS")
    max_active_jobs_per_user: int = Field(default=2, alias="DOCMOLDER_MAX_ACTIVE_JOBS_PER_USER")
    cleanup_interval_minutes: int = Field(default=30, alias="DOCMOLDER_CLEANUP_INTERVAL_MINUTES")
    stale_job_retention_hours: int = Field(default=6, alias="DOCMOLDER_STALE_JOB_RETENTION_HOURS")
    job_history_retention_days: int = Field(default=30, alias="DOCMOLDER_JOB_HISTORY_RETENTION_DAYS")
    ghostscript_timeout_seconds: int = Field(default=120, alias="DOCMOLDER_GHOSTSCRIPT_TIMEOUT_SECONDS")
    admin_daily_report_hour: int = Field(default=8, alias="DOCMOLDER_ADMIN_DAILY_REPORT_HOUR")
    admin_weekly_report_day: int = Field(default=0, alias="DOCMOLDER_ADMIN_WEEKLY_REPORT_DAY")
    admin_weekly_report_hour: int = Field(default=8, alias="DOCMOLDER_ADMIN_WEEKLY_REPORT_HOUR")
    admin_alert_window_minutes: int = Field(default=30, alias="DOCMOLDER_ADMIN_ALERT_WINDOW_MINUTES")
    admin_alert_min_finished_jobs: int = Field(default=4, alias="DOCMOLDER_ADMIN_ALERT_MIN_FINISHED_JOBS")
    admin_alert_failure_rate_percent: int = Field(default=60, alias="DOCMOLDER_ADMIN_ALERT_FAILURE_RATE_PERCENT")
    admin_alert_repeated_failures_threshold: int = Field(
        default=3,
        alias="DOCMOLDER_ADMIN_ALERT_REPEATED_FAILURES_THRESHOLD",
    )
    admin_alert_cooldown_minutes: int = Field(default=60, alias="DOCMOLDER_ADMIN_ALERT_COOLDOWN_MINUTES")
    health_max_queued_jobs: int = Field(default=20, alias="DOCMOLDER_HEALTH_MAX_QUEUED_JOBS")
    health_max_running_jobs: int = Field(default=5, alias="DOCMOLDER_HEALTH_MAX_RUNNING_JOBS")
    health_max_running_job_age_seconds: int = Field(
        default=3600,
        alias="DOCMOLDER_HEALTH_MAX_RUNNING_JOB_AGE_SECONDS",
    )
    health_max_runtime_dir_bytes: int = Field(default=2_147_483_648, alias="DOCMOLDER_HEALTH_MAX_RUNTIME_DIR_BYTES")
    health_max_backup_age_seconds: int = Field(default=172800, alias="DOCMOLDER_HEALTH_MAX_BACKUP_AGE_SECONDS")
    health_min_disk_free_bytes: int = Field(default=536_870_912, alias="DOCMOLDER_HEALTH_MIN_DISK_FREE_BYTES")
    health_min_disk_free_percent: int = Field(default=10, alias="DOCMOLDER_HEALTH_MIN_DISK_FREE_PERCENT")
    health_max_load_per_cpu: float = Field(default=2.0, alias="DOCMOLDER_HEALTH_MAX_LOAD_PER_CPU")
    health_min_memory_available_bytes: int = Field(
        default=134_217_728,
        alias="DOCMOLDER_HEALTH_MIN_MEMORY_AVAILABLE_BYTES",
    )
    image_pdf_max_source_side_px: int = Field(default=3200, alias="DOCMOLDER_IMAGE_PDF_MAX_SOURCE_SIDE_PX")
    runtime_dir: Path = Field(default=Path("./data/runtime"), alias="DOCMOLDER_RUNTIME_DIR")
    database_path: Path = Field(default=Path("./data/runtime/docmolder.db"), alias="DOCMOLDER_DATABASE_PATH")
    sqlite_backup_dir: Path = Field(default=Path("./data/runtime/backups"), alias="DOCMOLDER_SQLITE_BACKUP_DIR")
    sqlite_backup_retention_days: int = Field(default=7, alias="DOCMOLDER_SQLITE_BACKUP_RETENTION_DAYS")
    telegram_brand_sync_enabled: bool = Field(default=True, alias="DOCMOLDER_TELEGRAM_BRAND_SYNC_ENABLED")

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
        self.sqlite_backup_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_dirs()
    return settings
