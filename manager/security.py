"""Shared request-auth helpers for the blueprints."""
from __future__ import annotations

from functools import wraps

from flask import redirect, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "admin" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def current_admin() -> str | None:
    return session.get("admin")
