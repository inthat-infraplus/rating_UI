"""SQLAlchemy engine, session factory, and DB initialization.

Supports Postgres (via psycopg 3) and SQLite. Pick one with env var:

    DATABASE_URL=postgres://user:pass@host:5432/dbname     (Heroku-style — auto-normalized)
    DATABASE_URL=postgresql://user:pass@host:5432/dbname
    DATABASE_URL=sqlite:///./rating_ui.db

If DATABASE_URL is unset, defaults to a local SQLite file at <repo>/rating_ui.db
(or RATING_UI_DB env var).
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .db_migrations import initialize_database

BASE_DIR = Path(__file__).resolve().parent.parent


def _normalize_db_url(raw: str) -> str:
    """Normalize a DATABASE_URL to a SQLAlchemy-compatible form.

    - `postgres://`         → `postgresql+psycopg://`  (SQLAlchemy 2 rejects bare `postgres://`)
    - `postgresql://`       → `postgresql+psycopg://`  (force psycopg 3 over default psycopg2)
    - `postgresql+psycopg2` → leave alone (user explicitly chose)
    - others (sqlite, mysql, …) untouched
    """
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://") and "+" not in raw.split("://", 1)[0]:
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]
    return raw


def _resolve_db_url() -> str:
    explicit = os.environ.get("DATABASE_URL", "").strip()
    if explicit:
        return _normalize_db_url(explicit)
    sqlite_path = Path(os.environ.get("RATING_UI_DB", BASE_DIR / "rating_ui.db"))
    return f"sqlite:///{sqlite_path.as_posix()}"


DB_URL = _resolve_db_url()
IS_SQLITE = DB_URL.startswith("sqlite")

# SQLite needs check_same_thread=False so FastAPI's threadpool can share connections.
# Postgres handles its own pooling — pass nothing.
_connect_args: dict = {"check_same_thread": False} if IS_SQLITE else {}

engine = create_engine(
    DB_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,  # cheap reconnect on stale Postgres connections
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Initialize the database without rebuilding existing schema/data."""
    # Import models so they register on Base.metadata
    from . import models_db  # noqa: F401

    sqlite_path: Path | None = None
    if IS_SQLITE:
        sqlite_path = Path(DB_URL.replace("sqlite:///", "", 1))
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    initialize_database(engine, Base.metadata, sqlite_path=sqlite_path)


def ensure_postgres_database() -> bool:
    """If using Postgres and the target database doesn't exist, create it.

    Connects to the server's default `postgres` admin DB with the same credentials
    and runs CREATE DATABASE. Returns True if the database was created, False if it
    already existed. Raises if not Postgres or on any error.
    """
    if IS_SQLITE:
        raise RuntimeError("ensure_postgres_database() only applies when using Postgres.")

    parts = urlsplit(DB_URL)
    target_db = parts.path.lstrip("/")
    if not target_db:
        raise RuntimeError("DATABASE_URL must include a database name.")

    # Build admin URL pointing at the `postgres` system DB
    admin_url = urlunsplit(
        (parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment)
    )
    admin_engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        from sqlalchemy import text
        with admin_engine.connect() as conn:
            existing = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": target_db},
            ).scalar()
            if existing:
                return False
            # Identifier interpolation — pg won't accept :param for DB names.
            # Reject anything outside [A-Za-z0-9_] to prevent injection.
            if not all(c.isalnum() or c == "_" for c in target_db):
                raise RuntimeError(
                    f"Refusing to CREATE DATABASE {target_db!r}: "
                    "name must be alphanumeric/underscore only."
                )
            conn.execute(text(f'CREATE DATABASE "{target_db}"'))
            return True
    finally:
        admin_engine.dispose()


@contextmanager
def db_session() -> Iterator[Session]:
    """Context-managed DB session that commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
