"""SQLite storage for manager metadata (never for OS/SSH credentials).

Two kinds of data live here:
  * admin_users   -- panel login accounts (web manager auth only)
  * managed_users -- bookkeeping about which OS accounts this project
                      created, so destructive actions can never touch an
                      account the panel didn't create (root, service
                      accounts, pre-existing human accounts, ...).
  * audit_log     -- append-only record of privileged actions taken
                      through the panel/CLI.

SSH authentication itself is always handled by the real OS user database
(/etc/passwd, /etc/shadow) via the privileged helper -- this file never
stores an SSH-usable secret.
"""
from __future__ import annotations

import contextlib
import sqlite3
import time
from typing import Iterator

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    last_login_at   INTEGER,
    must_change_pw  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS managed_users (
    username        TEXT PRIMARY KEY,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    expires_at      INTEGER,
    max_sessions    INTEGER,
    enabled         INTEGER NOT NULL DEFAULT 1,
    note            TEXT,
    created_by      TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target      TEXT,
    detail      TEXT,
    success     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""

SCHEMA_VERSION = "1"


def connect() -> sqlite3.Connection:
    paths.ensure_dirs()
    conn = sqlite3.connect(str(paths.DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', ?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()
    try:
        paths.DB_FILE.chmod(0o640)
    except OSError:
        pass
    # init_db() can run as root (the installer, update.sh, or `ssh-ws`
    # itself, e.g. on a fresh/deleted database) as well as unprivileged
    # (the web panel's own first request) -- see config.py's save() for
    # the same reasoning and the real bug this class of fix addresses.
    paths.chown_to_service_user(paths.DB_FILE)


@contextlib.contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    conn = connect()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def log_action(actor: str, action: str, target: str | None, detail: str | None, success: bool) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log (ts, actor, action, target, detail, success) VALUES (?, ?, ?, ?, ?, ?)",
            (int(time.time()), actor, action, target, detail, 1 if success else 0),
        )
