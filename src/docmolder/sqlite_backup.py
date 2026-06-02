from __future__ import annotations

import argparse
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote


def backup_sqlite_database(
    db_path: Path,
    backup_dir: Path,
    *,
    retention_days: int = 7,
    timestamp: datetime | None = None,
) -> Path:
    source_path = db_path.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Database non trovato: {source_path}")

    backup_root = backup_dir.expanduser().resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    current_time = timestamp or datetime.now(timezone.utc)
    backup_path = backup_root / _build_backup_name(source_path, current_time)

    with _connect_read_only(source_path) as source, closing(sqlite3.connect(backup_path)) as destination:
        source.backup(destination)
        destination.commit()

    _validate_sqlite_database(backup_path)
    _prune_old_backups(backup_root, source_path, retention_days=retention_days, now=current_time)
    return backup_path


def restore_sqlite_database(
    backup_path: Path,
    db_path: Path,
    *,
    timestamp: datetime | None = None,
) -> Path | None:
    source_backup_path = backup_path.expanduser().resolve()
    if not source_backup_path.exists():
        raise FileNotFoundError(f"Backup SQLite non trovato: {source_backup_path}")

    target_path = db_path.expanduser().resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    restore_time = timestamp or datetime.now(timezone.utc)
    temp_target_path = target_path.with_suffix(f"{target_path.suffix}.restore-tmp")

    with _connect_read_only(source_backup_path) as source, closing(sqlite3.connect(temp_target_path)) as destination:
        source.backup(destination)
        destination.commit()

    _validate_sqlite_database(temp_target_path)

    previous_backup_path: Path | None = None
    if target_path.exists():
        previous_backup_path = target_path.with_name(
            f"{target_path.stem}.before-restore-{restore_time.strftime('%Y%m%d-%H%M%S')}{target_path.suffix}"
        )
        os.replace(target_path, previous_backup_path)
    os.replace(temp_target_path, target_path)
    return previous_backup_path


def _validate_sqlite_database(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None or row[0] != "ok":
        raise RuntimeError(f"Verifica integrity_check fallita per {db_path}")


def _prune_old_backups(
    backup_dir: Path,
    db_path: Path,
    *,
    retention_days: int,
    now: datetime,
) -> None:
    if retention_days < 0:
        return

    threshold = now - timedelta(days=retention_days)
    prefix = f"{db_path.stem}-"
    suffix = f"{db_path.suffix}.backup"
    for candidate in backup_dir.iterdir():
        if not candidate.is_file():
            continue
        if not candidate.name.startswith(prefix) or not candidate.name.endswith(suffix):
            continue
        modified_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
        if modified_at < threshold:
            candidate.unlink(missing_ok=True)


def _build_backup_name(db_path: Path, timestamp: datetime) -> str:
    return f"{db_path.stem}-{timestamp.strftime('%Y%m%d-%H%M%S')}{db_path.suffix}.backup"


@contextmanager
def _connect_read_only(db_path: Path):
    quoted_path = quote(str(db_path))
    connection = sqlite3.connect(f"file:{quoted_path}?mode=ro", uri=True)
    try:
        yield connection
    finally:
        connection.close()


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup e restore del database SQLite di DocMolder.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Crea un backup verificato del database.")
    backup_parser.add_argument("--db-path", type=Path, required=True)
    backup_parser.add_argument("--backup-dir", type=Path, required=True)
    backup_parser.add_argument("--retention-days", type=int, default=7)

    restore_parser = subparsers.add_parser("restore", help="Ripristina il database da un backup verificato.")
    restore_parser.add_argument("--backup-path", type=Path, required=True)
    restore_parser.add_argument("--db-path", type=Path, required=True)

    return parser


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    if args.command == "backup":
        backup_path = backup_sqlite_database(
            args.db_path,
            args.backup_dir,
            retention_days=args.retention_days,
        )
        print(backup_path)
        return

    previous_backup_path = restore_sqlite_database(args.backup_path, args.db_path)
    if previous_backup_path is not None:
        print(previous_backup_path)
    else:
        print(args.db_path)


if __name__ == "__main__":
    main()
