from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


logger = logging.getLogger(__name__)


def create_job_dir(runtime_dir: Path, user_id: int) -> Path:
    job_dir = runtime_dir / "jobs" / f"user_{user_id}_{uuid.uuid4().hex[:12]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def cleanup_job_dir(job_dir: Path) -> None:
    try:
        shutil.rmtree(job_dir)
    except FileNotFoundError:
        return
    except OSError:
        logger.exception("Impossibile ripulire la cartella temporanea del job %s", job_dir)


def cleanup_stale_job_dirs(runtime_dir: Path, max_age_hours: int) -> int:
    jobs_dir = runtime_dir / "jobs"
    if not jobs_dir.exists():
        return 0
    threshold = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    removed_count = 0
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        try:
            modified_at = datetime.fromtimestamp(job_dir.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if modified_at > threshold:
            continue
        try:
            shutil.rmtree(job_dir, ignore_errors=False)
            removed_count += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.exception("Impossibile ripulire la cartella temporanea %s", job_dir)
    return removed_count
