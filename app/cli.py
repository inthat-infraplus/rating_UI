"""Command-line tools: seed users, init DB.

Usage:
    python -m app.cli init-db
    python -m app.cli create-user --username admin --role L1
    python -m app.cli create-user --username alice --role L2 --display-name "Alice" --password secret
    python -m app.cli list-users
    python -m app.cli set-password --username admin
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from .auth import hash_password
from .db import db_session, init_db
from .models_db import User, UserRole


def _prompt_password() -> str:
    pw1 = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Confirm:  ")
    if pw1 != pw2:
        print("Passwords do not match.", file=sys.stderr)
        sys.exit(1)
    if len(pw1) < 6:
        print("Password must be at least 6 characters.", file=sys.stderr)
        sys.exit(1)
    return pw1


def cmd_init_db(_args: argparse.Namespace) -> int:
    init_db()
    print("DB initialized.")
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    init_db()
    role = UserRole(args.role)
    password = args.password or _prompt_password()
    display = args.display_name or args.username

    with db_session() as db:
        existing = db.scalars(select(User).where(User.username == args.username)).first()
        if existing is not None:
            print(f"User {args.username!r} already exists.", file=sys.stderr)
            return 1
        user = User(
            username=args.username,
            password_hash=hash_password(password),
            display_name=display,
            role=role,
        )
        db.add(user)

    print(f"Created user {args.username!r} (role={role.value}).")
    return 0


def cmd_list_users(_args: argparse.Namespace) -> int:
    init_db()
    with db_session() as db:
        users = db.scalars(select(User).order_by(User.id)).all()
        if not users:
            print("(no users)")
            return 0
        print(f"{'ID':<4} {'USERNAME':<20} {'ROLE':<6} {'DISPLAY NAME':<24} LAST LOGIN")
        for u in users:
            last = u.last_login_at.isoformat(timespec="seconds") if u.last_login_at else "-"
            print(f"{u.id:<4} {u.username:<20} {u.role.value:<6} {u.display_name:<24} {last}")
    return 0


def cmd_set_password(args: argparse.Namespace) -> int:
    init_db()
    password = args.password or _prompt_password()
    with db_session() as db:
        user = db.scalars(select(User).where(User.username == args.username)).first()
        if user is None:
            print(f"User {args.username!r} not found.", file=sys.stderr)
            return 1
        user.password_hash = hash_password(password)
    print(f"Password updated for {args.username!r}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create database tables.").set_defaults(func=cmd_init_db)

    p_create = sub.add_parser("create-user", help="Create a new user.")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--role", required=True, choices=["L1", "L2"])
    p_create.add_argument("--display-name", default=None)
    p_create.add_argument("--password", default=None, help="If omitted, prompts interactively.")
    p_create.set_defaults(func=cmd_create_user)

    sub.add_parser("list-users", help="List all users.").set_defaults(func=cmd_list_users)

    p_setpw = sub.add_parser("set-password", help="Reset a user's password.")
    p_setpw.add_argument("--username", required=True)
    p_setpw.add_argument("--password", default=None)
    p_setpw.set_defaults(func=cmd_set_password)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
