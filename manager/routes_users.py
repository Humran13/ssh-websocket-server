from __future__ import annotations

import time

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import users
from security import current_admin, login_required

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/")
@login_required
def index():
    return render_template("users.html", users=users.list_users(), now=int(time.time()))


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password") or users.generate_password()
        max_sessions = request.form.get("max_sessions") or None
        expiry_days = request.form.get("expiry_days") or None
        note = request.form.get("note", "").strip() or None
        try:
            expires_at = int(time.time()) + int(expiry_days) * 86400 if expiry_days else None
            new_user = users.create_user(
                username, password, current_admin(),
                expires_at=expires_at,
                max_sessions=int(max_sessions) if max_sessions else None,
                note=note,
            )
            flash(f"User '{new_user.username}' created. Password: {password} "
                  f"(shown once -- store it now).", "success")
            return redirect(url_for("users.index"))
        except (users.UserError, ValueError) as exc:
            flash(str(exc), "error")
    return render_template("user_create.html")


@bp.route("/<username>/password", methods=["POST"])
@login_required
def set_password(username):
    password = request.form.get("password") or users.generate_password()
    try:
        users.set_password(username, password, current_admin())
        flash(f"Password for '{username}' changed to: {password} (shown once).", "success")
    except users.UserError as exc:
        flash(str(exc), "error")
    return redirect(url_for("users.index"))


@bp.route("/<username>/disable", methods=["POST"])
@login_required
def disable(username):
    try:
        users.disable_user(username, current_admin())
        flash(f"User '{username}' disabled.", "success")
    except users.UserError as exc:
        flash(str(exc), "error")
    return redirect(url_for("users.index"))


@bp.route("/<username>/enable", methods=["POST"])
@login_required
def enable(username):
    try:
        users.enable_user(username, current_admin())
        flash(f"User '{username}' enabled.", "success")
    except users.UserError as exc:
        flash(str(exc), "error")
    return redirect(url_for("users.index"))


@bp.route("/<username>/delete", methods=["POST"])
@login_required
def delete(username):
    confirm = request.form.get("confirm_username", "") == username
    try:
        users.delete_user(username, current_admin(), confirm=confirm)
        flash(f"User '{username}' deleted.", "success")
    except users.UserError as exc:
        flash(str(exc), "error")
    return redirect(url_for("users.index"))


@bp.route("/<username>/expiry", methods=["POST"])
@login_required
def expiry(username):
    action = request.form.get("action")
    try:
        if action == "remove":
            users.remove_expiry(username, current_admin())
        elif action == "extend":
            days = int(request.form.get("days", "0") or 0)
            users.extend_expiry(username, days * 86400, current_admin())
        elif action == "set":
            days = int(request.form.get("days", "0") or 0)
            users.set_expiry(username, int(time.time()) + days * 86400, current_admin())
        flash(f"Expiry updated for '{username}'.", "success")
    except (users.UserError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("users.index"))


@bp.route("/<username>/max-sessions", methods=["POST"])
@login_required
def max_sessions(username):
    value = request.form.get("max_sessions") or None
    try:
        users.set_max_sessions(username, int(value) if value else None, current_admin())
        flash(f"Session limit updated for '{username}'.", "success")
    except (users.UserError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("users.index"))


@bp.route("/sessions")
@login_required
def sessions():
    return render_template("sessions.html", sessions=users.list_active_sessions())


@bp.route("/sessions/<username>/<int:pid>/disconnect", methods=["POST"])
@login_required
def disconnect(username, pid):
    try:
        users.disconnect_session(username, pid, current_admin())
        flash(f"Disconnected session for '{username}'.", "success")
    except users.UserError as exc:
        flash(str(exc), "error")
    return redirect(url_for("users.sessions"))
