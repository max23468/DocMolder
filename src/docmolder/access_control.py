from __future__ import annotations

from typing import Protocol

from docmolder.config import Settings
from docmolder.session_store import SessionStore

ACCESS_META_PREFIX = "access:"
ACCESS_STATUS_PENDING = "pending"
ACCESS_STATUS_APPROVED = "approved"
ACCESS_STATUS_BLOCKED = "blocked"
ACCESS_STATUS_REJECTED = "rejected"


class AccessControlDependencies(Protocol):
    settings: Settings
    session_store: SessionStore


def is_authorized(user_id: int | None, settings: Settings) -> bool:
    if user_id is None:
        return False
    if not settings.allowed_user_ids:
        return True
    return user_id in settings.allowed_user_ids


def access_meta_key(user_id: int) -> str:
    return f"{ACCESS_META_PREFIX}{user_id}:status"


def get_dynamic_access_status(deps: AccessControlDependencies, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    value = deps.session_store.get_meta(access_meta_key(user_id))
    return value.strip().lower() if value else None


def set_dynamic_access_status(deps: AccessControlDependencies, user_id: int, status: str) -> None:
    deps.session_store.set_meta(access_meta_key(user_id), status)


def is_authorized_for_deps(user_id: int | None, deps: AccessControlDependencies) -> bool:
    if user_id is None:
        return False
    if is_admin(user_id, deps.settings):
        return True
    dynamic_status = get_dynamic_access_status(deps, user_id)
    if dynamic_status in {ACCESS_STATUS_BLOCKED, ACCESS_STATUS_REJECTED}:
        return False
    if dynamic_status == ACCESS_STATUS_APPROVED:
        return True
    return is_authorized(user_id, deps.settings)


def list_dynamic_access_statuses(deps: AccessControlDependencies) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for key, value in deps.session_store.list_meta(ACCESS_META_PREFIX).items():
        suffix = key.removeprefix(ACCESS_META_PREFIX)
        raw_user_id = suffix.split(":", 1)[0]
        try:
            user_id = int(raw_user_id)
        except ValueError:
            continue
        entries.append((user_id, value))
    return sorted(entries, key=lambda item: item[0])


def is_admin(user_id: int | None, settings: Settings) -> bool:
    if user_id is None:
        return False
    return user_id in settings.admin_user_ids
