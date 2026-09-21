"""Flask session secret key: generated once, persisted, shared by every
gunicorn worker.

gunicorn's default (non-preload) mode imports the WSGI app separately in
each worker process, so a naive "if file missing, generate and write"
would race: with `-w 2`, both workers can observe "no file yet"
simultaneously and each compute a *different* random key, only one of
which ends up on disk -- leaving the two workers holding different
in-memory keys and silently invalidating each other's sessions depending
on which worker handles a given request.

`install.sh` calls `ensure()` once, as a single process, before any
gunicorn worker starts, which is what actually prevents the race in
practice. The atomic hard-link trick below is a second, independent
safety net for any other startup path (e.g. running the app directly in
development) where that pre-creation step didn't happen.
"""
from __future__ import annotations

import os
import secrets
import tempfile

from . import paths


def _atomic_create_if_missing(key_file) -> str:
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    # A unique-per-call temp filename is essential here: two concurrent
    # callers writing to the *same* fixed tmp path would truncate/clobber
    # each other's in-progress write before either reaches the os.link
    # step below, so the "winning" link could end up pointing at content
    # that doesn't match the key that call actually returns. mkstemp in
    # the same directory guarantees a distinct name and that the link
    # (same filesystem) is atomic.
    fd, tmp_str = tempfile.mkstemp(dir=str(key_file.parent), prefix=".secret_key.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key)
        os.chmod(tmp_str, 0o600)
        paths.chown_to_service_user(tmp_str)
        try:
            # Atomic "create key_file only if it doesn't already exist":
            # os.link fails with FileExistsError if a concurrent process
            # already won this race, and by the time it can succeed or
            # fail, tmp's content is already fully written and closed, so
            # there is no window where a reader could see a partial file.
            # The link shares tmp's inode, so it also shares the ownership
            # set above -- there is no separate chown-after-link needed.
            os.link(tmp_str, key_file)
            return key
        except FileExistsError:
            return key_file.read_text(encoding="utf-8").strip()
    finally:
        if os.path.exists(tmp_str):
            os.remove(tmp_str)


def ensure() -> str:
    """Return the persisted key, creating it exactly once if missing."""
    key_file = paths.ETC_DIR / "secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return _atomic_create_if_missing(key_file)
