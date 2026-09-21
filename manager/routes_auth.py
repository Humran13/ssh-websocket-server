from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core import auth
from rate_limit import limiter

bp = Blueprint("auth", __name__)


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if auth.has_any_admin():
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if password != confirm:
            flash("Passwords do not match.", "error")
        else:
            try:
                auth.create_admin(username, password)
                flash("Admin account created. Please log in.", "success")
                return redirect(url_for("auth.login"))
            except auth.AuthError as exc:
                flash(str(exc), "error")
    return render_template("setup.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/5minutes")
def login():
    if not auth.has_any_admin():
        return redirect(url_for("auth.setup"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if auth.verify_login(username, password):
            session.clear()
            session["admin"] = username
            session.permanent = True
            return redirect(url_for("dashboard.index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
