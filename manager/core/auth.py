"""Admin (panel login) account handling. Separate from managed SSH users."""
from __future__ import annotations

import time

from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class AuthError(ValueError):
    pass


def has_any_admin() -> bool:
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM admin_users")
        return cur.fetchone()["n"] > 0


def create_admin(username: str, password: str) -> None:
    if not username or len(username) < 3:
        raise AuthError("admin username must be at least 3 characters")
    if len(password) < 12:
        raise AuthError("admin password must be at least 12 characters")
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), int(time.time())),
        )


def verify_login(username: str, password: str) -> bool:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM admin_users WHERE username = ?", (username,))
        row = cur.fetchone()
    if row is None:
        # Still run a hash comparison to keep timing roughly constant
        # regardless of whether the username exists.
        check_password_hash(generate_password_hash("x"), password)
        return False
    ok = check_password_hash(row["password_hash"], password)
    if ok:
        with db.cursor() as cur:
            cur.execute("UPDATE admin_users SET last_login_at = ? WHERE username = ?",
                        (int(time.time()), username))
    return ok


def change_password(username: str, new_password: str) -> None:
    if len(new_password) < 12:
        raise AuthError("admin password must be at least 12 characters")
    with db.cursor() as cur:
        cur.execute("UPDATE admin_users SET password_hash = ?, must_change_pw = 0 WHERE username = ?",
                     (generate_password_hash(new_password), username))
