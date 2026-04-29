"""Lightweight schema migrations with SQLite snapshots and rollback.

This app currently ships with SQLite by default and no Alembic history.
The helpers in this module add just enough migration discipline to keep
developer updates from rebuilding the database or silently dropping data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Callable

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.engine import Connection, Engine

SCHEMA_TABLE = "schema_migrations"
APP_TABLES = {"users", "tasks", "task_events"}


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[Connection, MetaData], None]


def _migration_001_baseline(connection: Connection, metadata: MetaData) -> None:
    """Create the current application schema for a fresh database."""
    metadata.create_all(bind=connection)


MIGRATIONS: list[Migration] = [
    Migration(1, "baseline_task_workflow_schema", _migration_001_baseline),
]


def latest_version() -> int:
    return MIGRATIONS[-1].version if MIGRATIONS else 0


def snapshot_directory(sqlite_path: Path) -> Path:
    return sqlite_path.parent / "db_snapshots"


def list_snapshots(sqlite_path: Path) -> list[Path]:
    backup_dir = snapshot_directory(sqlite_path)
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob(f"{sqlite_path.stem}_*.db"), reverse=True)


def create_sqlite_snapshot(sqlite_path: Path, *, label: str) -> Path:
    sqlite_path = sqlite_path.resolve()
    backup_dir = snapshot_directory(sqlite_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in label)
    snapshot_path = backup_dir / f"{sqlite_path.stem}_{timestamp}_{safe_label}.db"
    shutil.copy2(sqlite_path, snapshot_path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{sqlite_path}{suffix}")
        if sidecar.exists():
            shutil.copy2(sidecar, Path(f"{snapshot_path}{suffix}"))
    return snapshot_path


def restore_sqlite_snapshot(sqlite_path: Path, snapshot_path: Path) -> Path:
    sqlite_path = sqlite_path.resolve()
    snapshot_path = snapshot_path.resolve()
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot_path, sqlite_path)
    for suffix in ("-wal", "-shm"):
        live_sidecar = Path(f"{sqlite_path}{suffix}")
        snap_sidecar = Path(f"{snapshot_path}{suffix}")
        if snap_sidecar.exists():
            shutil.copy2(snap_sidecar, live_sidecar)
        elif live_sidecar.exists():
            live_sidecar.unlink()
    return sqlite_path


def _ensure_schema_table(connection: Connection) -> None:
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                backup_path TEXT
            )
            """
        )
    )


def _current_version(connection: Connection) -> int:
    result = connection.execute(text(f"SELECT MAX(version) FROM {SCHEMA_TABLE}")).scalar()
    return int(result or 0)


def _record_migration(
    connection: Connection,
    *,
    version: int,
    name: str,
    backup_path: str | None,
) -> None:
    connection.execute(
        text(
            f"""
            INSERT INTO {SCHEMA_TABLE} (version, name, applied_at, backup_path)
            VALUES (:version, :name, :applied_at, :backup_path)
            """
        ),
        {
            "version": version,
            "name": name,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "backup_path": backup_path,
        },
    )


def _has_app_tables(engine: Engine) -> bool:
    table_names = set(inspect(engine).get_table_names())
    return bool(table_names & APP_TABLES)


def _has_schema_table(engine: Engine) -> bool:
    return inspect(engine).has_table(SCHEMA_TABLE)


def initialize_database(
    engine: Engine,
    metadata: MetaData,
    *,
    sqlite_path: Path | None = None,
) -> None:
    """Apply schema migrations without rebuilding an existing database.

    Legacy databases that predate migration tracking are stamped at the
    current version instead of being rebuilt. SQLite databases are snapshotted
    before each migration and restored automatically if a migration fails.
    """
    if not _has_schema_table(engine):
        if _has_app_tables(engine):
            with engine.begin() as connection:
                _ensure_schema_table(connection)
                if latest_version():
                    _record_migration(
                        connection,
                        version=latest_version(),
                        name="legacy_schema_stamp",
                        backup_path=None,
                    )
            return
        # Fresh database: fall through and run migrations from version 0.

    with engine.begin() as connection:
        _ensure_schema_table(connection)
        current_version = _current_version(connection)

    if current_version > latest_version():
        raise RuntimeError(
            f"Database schema version {current_version} is newer than this app supports "
            f"(latest known migration: {latest_version()})."
        )

    pending = [migration for migration in MIGRATIONS if migration.version > current_version]
    for migration in pending:
        backup_path: Path | None = None
        if sqlite_path is not None and sqlite_path.exists():
            engine.dispose()
            backup_path = create_sqlite_snapshot(
                sqlite_path,
                label=f"before_v{migration.version}_{migration.name}",
            )
        try:
            with engine.begin() as connection:
                _ensure_schema_table(connection)
                migration.apply(connection, metadata)
                _record_migration(
                    connection,
                    version=migration.version,
                    name=migration.name,
                    backup_path=str(backup_path) if backup_path else None,
                )
        except Exception as exc:
            if backup_path is not None and sqlite_path is not None:
                engine.dispose()
                restore_sqlite_snapshot(sqlite_path, backup_path)
            raise RuntimeError(
                f"Database migration v{migration.version} ({migration.name}) failed."
            ) from exc
