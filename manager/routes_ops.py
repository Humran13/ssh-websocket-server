from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from core import backup, health, logs, paths, privileged
from security import current_admin, login_required

bp = Blueprint("ops", __name__)


@bp.route("/logs")
@login_required
def logs_view():
    source = request.args.get("source", "manager")
    if source not in logs.available_sources():
        source = "manager"
    lines = logs.tail(source, 200)
    return render_template("logs.html", source=source, sources=logs.available_sources(), lines=lines)


@bp.route("/health")
@login_required
def health_view():
    return render_template("health.html", results=health.run_all())


@bp.route("/backup", methods=["GET", "POST"])
@login_required
def backup_view():
    if request.method == "POST":
        include_ssl = "include_ssl" in request.form
        try:
            path = backup.create_backup(include_ssl=include_ssl, actor=current_admin())
            flash(f"Backup created: {path.name}", "success")
        except backup.BackupError as exc:
            flash(str(exc), "error")
    return render_template("backup.html", backups=backup.list_backups())


@bp.route("/backup/<name>/download")
@login_required
def backup_download(name):
    safe_name = secure_filename(name)
    path = paths.BACKUP_DIR / safe_name
    if not path.is_file() or path.parent != paths.BACKUP_DIR:
        abort(404)
    return send_file(path, as_attachment=True, download_name=safe_name)


@bp.route("/backup/<name>/restore", methods=["POST"])
@login_required
def backup_restore(name):
    safe_name = secure_filename(name)
    path = paths.BACKUP_DIR / safe_name
    if not path.is_file() or path.parent != paths.BACKUP_DIR:
        abort(404)
    try:
        result = backup.restore_backup(path)
        flash(f"Restored from {safe_name}. Safety backup saved as "
              f"{Path(result['safety_backup']).name}. Restart services to apply.", "success")
    except backup.BackupError as exc:
        flash(str(exc), "error")
    return redirect(url_for("ops.backup_view"))


@bp.route("/services/restart/<name>", methods=["POST"])
@login_required
def restart_service(name):
    from scripts_allowlist import MANAGED_SERVICES
    if name not in MANAGED_SERVICES:
        abort(400)
    try:
        privileged.call("service_restart", {"name": name})
        flash(f"Service '{name}' restarted.", "success")
    except privileged.PrivilegedActionError as exc:
        flash(str(exc), "error")
    # Always redirect to a fixed, known page rather than trusting the
    # Referer header -- a redirect target should never be attacker/
    # browser-controlled input, however low-risk that seems here.
    return redirect(url_for("dashboard.index"))
