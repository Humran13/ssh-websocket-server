from __future__ import annotations

from flask import Blueprint, render_template

from core import config as config_mod
from core import domain, system_info, users, version
from security import login_required

bp = Blueprint("dashboard", __name__)


@bp.route("/dashboard")
@login_required
def index():
    cfg = config_mod.load()
    osr = system_info.os_release()
    mem = system_info.memory_usage()
    disk = system_info.disk_usage("/")
    uptime = system_info.uptime_seconds()

    cert = domain.certificate_status()

    data = {
        "cfg": cfg,
        "hostname": system_info.hostname(),
        "public_ip": system_info.public_ip(),
        "os_name": osr.get("PRETTY_NAME", "Unknown"),
        "kernel": system_info.kernel(),
        "uptime_seconds": uptime,
        "cpu_percent": system_info.cpu_percent(),
        "memory": mem,
        "disk": disk,
        "sshd_status": system_info.service_status("ssh"),
        "bridge_status": system_info.service_status("sshws-bridge"),
        "nginx_status": system_info.service_status("nginx"),
        "manager_status": system_info.service_status("sshws-manager"),
        "firewall_active": system_info.firewall_status(),
        "cert": cert,
        "active_sessions": users.list_active_sessions(),
        "managed_user_count": len(users.list_users()),
        "installed_version": version.installed_version(),
    }
    return render_template("dashboard.html", **data)
