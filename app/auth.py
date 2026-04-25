"""Authentication: password hashing, login/logout, session, role guards."""
from __future__ import annotations

import os
from datetime import datetime
from functools import wraps
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy import select

from .db import db_session
from .models_db import User, UserRole

# bcrypt rounds=12 is a sane default (~250ms per hash on modern CPUs)
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

SESSION_USER_ID_KEY = "user_id"


def get_secret_key() -> str:
    """Session-signing key. Required in prod via RATING_UI_SECRET_KEY env var."""
    key = os.environ.get("RATING_UI_SECRET_KEY")
    if key:
        return key
    # Dev fallback — print warning so it's obvious in logs
    print(
        "[auth] WARNING: RATING_UI_SECRET_KEY not set. Using insecure dev key. "
        "Set the env var before running in production.",
        flush=True,
    )
    return "dev-insecure-do-not-use-in-prod"


# --- password helpers ---

def hash_password(plaintext: str) -> str:
    return _pwd_ctx.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(plaintext, hashed)
    except Exception:
        return False


# --- session helpers (Starlette SessionMiddleware exposes request.session dict) ---

def login_user(request: Request, user: User) -> None:
    request.session[SESSION_USER_ID_KEY] = user.id
    with db_session() as db:
        db_user = db.get(User, user.id)
        if db_user is not None:
            db_user.last_login_at = datetime.utcnow()


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_USER_ID_KEY, None)


def current_user(request: Request) -> User | None:
    """Return the currently logged-in user, or None if anonymous."""
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if not user_id:
        return None
    with db_session() as db:
        user = db.get(User, user_id)
        if user is None:
            # Stale session — clear it
            request.session.pop(SESSION_USER_ID_KEY, None)
            return None
        # Detach so callers can use attributes after the session closes
        db.expunge(user)
        return user


# --- guards (raise 401/403; FastAPI handlers can call directly or use as deps) ---

def require_user(request: Request) -> User:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def require_role(*roles: UserRole) -> Callable[[Request], User]:
    """FastAPI dependency: ensures the request's user has one of the given roles."""
    def _dep(request: Request) -> User:
        user = require_user(request)
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden — insufficient role.")
        return user
    return _dep


# --- API auth helper ---

def authenticate(username: str, password: str) -> User | None:
    """Validate credentials. Returns user on success, None otherwise."""
    if not username or not password:
        return None
    with db_session() as db:
        user = db.scalars(select(User).where(User.username == username)).first()
        if user is None or not verify_password(password, user.password_hash):
            return None
        db.expunge(user)
        return user
