from __future__ import annotations

import logging
import uuid


def _normalize_log_value(value: object) -> str:
    if value is None:
        return "none"
    text = str(value).strip()
    if not text:
        return '""'
    return text.replace("\n", "\\n").replace(" ", "_")


def format_log_context(event: str, **fields: object) -> str:
    parts = [f"event={_normalize_log_value(event)}"]
    for key in sorted(fields):
        parts.append(f"{key}={_normalize_log_value(fields[key])}")
    return " ".join(parts)


def generate_operation_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def log_event(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    logger.log(level, format_log_context(event, **fields))
