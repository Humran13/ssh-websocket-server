"""Managed SSH user lifecycle: the same functions back both the web panel
and the CLI. Business rules (e.g. "only accounts we created can be
deleted") live here exactly once.
"""
from __future__ import annotations

import re
import secrets
import string
import time
from dataclasses import dataclass

from . import db, privileged

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")


class UserError(ValueError):
    pass


@dataclass
class ManagedUser:
    username: str
    created_at: int
    updated_at: int
    expires_at: int | None
    max_sessions: int | None
    enabled: bool
    note: str | None
    created_by: str | None

    @property
    def expired(self) -> bool:
        return bool(self.expires_at) and self.expires_at < int(time.time())


def validate_username(username: str) -> str:
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise UserError(
            "username must be 3-32 lowercase letters, digits, '_' or '-', "
            "and start with a letter"
        )
    return username


def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^*_-+="
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)):
            return pw


def list_users() -> list[ManagedUser]:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM managed_users ORDER BY username")
        rows = cur.fetchall()
    return [_row_to_user(r) for r in rows]


def get_user(username: str) -> ManagedUser | None:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM managed_users WHERE username = ?", (username,))
        row = cur.fetchone()
    return _row_to_user(row) if row else None


def _row_to_user(row) -> ManagedUser:
    return ManagedUser(
        username=row["username"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        max_sessions=row["max_sessions"],
        enabled=bool(row["enabled"]),
        note=row["note"],
        created_by=row["created_by"],
    )


def create_user(username: str, password: str, actor: str, expires_at: int | None = None,
                 max_sessions: int | None = None, note: str | None = None) -> ManagedUser:
    validate_username(username)
    if get_user(username) is not None:
        raise UserError(f"'{username}' is already a managed user")

    try:
        privileged.call("user_create", {
            "username": username, "password": password, "expires_at": expires_at,
        })
        if max_sessions is not None:
            privileged.call("user_set_max_sessions", {"username": username, "max_sessions": max_sessions})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "user_create", username, str(exc), success=False)
        raise UserError(str(exc)) from exc

    now = int(time.time())
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO managed_users (username, created_at, updated_at, expires_at, "
            "max_sessions, enabled, note, created_by) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (username, now, now, expires_at, max_sessions, note, actor),
        )
    db.log_action(actor, "user_create", username, note, success=True)
    return get_user(username)


def _require_managed(username: str) -> ManagedUser:
    user = get_user(username)
    if user is None:
        raise UserError(f"'{username}' is not a managed user")
    return user


def set_password(username: str, password: str, actor: str) -> None:
    _require_managed(username)
    try:
        privileged.call("user_set_password", {"username": username, "password": password})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "user_set_password", username, str(exc), success=False)
        raise UserError(str(exc)) from exc
    _touch(username)
    db.log_action(actor, "user_set_password", username, None, success=True)


def disable_user(username: str, actor: str) -> None:
    _require_managed(username)
    try:
        privileged.call("user_disable", {"username": username})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "user_disable", username, str(exc), success=False)
        raise UserError(str(exc)) from exc
    with db.cursor() as cur:
        cur.execute("UPDATE managed_users SET enabled = 0, updated_at = ? WHERE username = ?",
                     (int(time.time()), username))
    db.log_action(actor, "user_disable", username, None, success=True)


def enable_user(username: str, actor: str) -> None:
    _require_managed(username)
    try:
        privileged.call("user_enable", {"username": username})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "user_enable", username, str(exc), success=False)
        raise UserError(str(exc)) from exc
    with db.cursor() as cur:
        cur.execute("UPDATE managed_users SET enabled = 1, updated_at = ? WHERE username = ?",
                     (int(time.time()), username))
    db.log_action(actor, "user_enable", username, None, success=True)


def delete_user(username: str, actor: str, confirm: bool) -> None:
    _require_managed(username)
    if not confirm:
        raise UserError("deletion requires explicit confirmation")
    try:
        privileged.call("user_delete", {"username": username})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "user_delete", username, str(exc), success=False)
        raise UserError(str(exc)) from exc
    with db.cursor() as cur:
        cur.execute("DELETE FROM managed_users WHERE username = ?", (username,))
    db.log_action(actor, "user_delete", username, None, success=True)


def set_expiry(username: str, expires_at: int | None, actor: str) -> None:
    _require_managed(username)
    try:
        privileged.call("user_set_expiry", {"username": username, "expires_at": expires_at})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "user_set_expiry", username, str(exc), success=False)
        raise UserError(str(exc)) from exc
    with db.cursor() as cur:
        cur.execute("UPDATE managed_users SET expires_at = ?, updated_at = ? WHERE username = ?",
                     (expires_at, int(time.time()), username))
    db.log_action(actor, "user_set_expiry", username, str(expires_at), success=True)


def extend_expiry(username: str, extra_seconds: int, actor: str) -> None:
    user = _require_managed(username)
    base = user.expires_at if user.expires_at and user.expires_at > int(time.time()) else int(time.time())
    set_expiry(username, base + extra_seconds, actor)


def remove_expiry(username: str, actor: str) -> None:
    set_expiry(username, None, actor)


def set_max_sessions(username: str, max_sessions: int | None, actor: str) -> None:
    _require_managed(username)
    try:
        privileged.call("user_set_max_sessions", {"username": username, "max_sessions": max_sessions})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "user_set_max_sessions", username, str(exc), success=False)
        raise UserError(str(exc)) from exc
    with db.cursor() as cur:
        cur.execute("UPDATE managed_users SET max_sessions = ?, updated_at = ? WHERE username = ?",
                     (max_sessions, int(time.time()), username))
    db.log_action(actor, "user_set_max_sessions", username, str(max_sessions), success=True)


def _touch(username: str) -> None:
    with db.cursor() as cur:
        cur.execute("UPDATE managed_users SET updated_at = ? WHERE username = ?",
                     (int(time.time()), username))


def list_active_sessions() -> list[dict]:
    managed = {u.username for u in list_users()}
    try:
        data = privileged.call("sessions_list", {})
    except privileged.PrivilegedActionError:
        return []
    return [s for s in data.get("sessions", []) if s["username"] in managed]


def disconnect_session(username: str, pid: int, actor: str) -> None:
    _require_managed(username)
    try:
        privileged.call("session_kill", {"username": username, "pid": pid})
    except privileged.PrivilegedActionError as exc:
        db.log_action(actor, "session_kill", username, str(exc), success=False)
        raise UserError(str(exc)) from exc
    db.log_action(actor, "session_kill", username, str(pid), success=True)
