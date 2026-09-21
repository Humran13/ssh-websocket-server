from __future__ import annotations

from flask import Blueprint, flash, render_template, request

from core import config as config_mod
from core import domain, firewall, network, ws_settings
from security import current_admin, login_required

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/websocket", methods=["GET", "POST"])
@login_required
def websocket():
    if request.method == "POST":
        form = request.form.get("form")
        try:
            if form == "paths":
                raw_paths = request.form.get("ws_paths", "")
                paths_list = [p.strip() for p in raw_paths.splitlines() if p.strip()]
                ws_settings.update_paths(paths_list, current_admin())
                flash("WebSocket paths updated.", "success")
            elif form == "enabled":
                ws_settings.set_enabled(
                    ws_enabled="ws_enabled" in request.form,
                    wss_enabled="wss_enabled" in request.form,
                    actor=current_admin(),
                )
                flash("WebSocket mode updated.", "success")
            elif form == "ports":
                ws_settings.update_ports(
                    ws_port=int(request.form["ws_port"]) if request.form.get("ws_port") else None,
                    wss_port=int(request.form["wss_port"]) if request.form.get("wss_port") else None,
                    bridge_port=int(request.form["bridge_port"]) if request.form.get("bridge_port") else None,
                    actor=current_admin(),
                )
                flash("Ports updated.", "success")
        except (ws_settings.WsSettingsError, config_mod.ConfigError, ValueError) as exc:
            flash(str(exc), "error")
    cfg = config_mod.load()
    return render_template("ws_settings.html", cfg=cfg)


@bp.route("/domain", methods=["GET", "POST"])
@login_required
def domain_settings():
    if request.method == "POST":
        form = request.form.get("form")
        try:
            if form == "set_domain":
                domain.set_domain(request.form.get("domain", "").strip(), current_admin())
                flash("Domain updated.", "success")
            elif form == "remove_domain":
                domain.remove_domain(current_admin())
                flash("Domain removed -- back to IP/WS mode.", "success")
            elif form == "issue_cert":
                email = request.form.get("email", "").strip() or None
                domain.issue_certificate(email, current_admin())
                flash("Certificate issued and WSS enabled.", "success")
            elif form == "renew_cert":
                from core import privileged
                result = privileged.call("certbot_renew", {}, timeout=200)
                flash("Renewal run: " + (result.get("output") or "ok"), "success")
        except (domain.DomainError, config_mod.ConfigError) as exc:
            flash(str(exc), "error")
    cfg = config_mod.load()
    cert = domain.certificate_status()
    dns = domain.dns_check(cfg["domain"]) if cfg["domain"] else None
    return render_template("domain_settings.html", cfg=cfg, cert=cert, dns=dns)


@bp.route("/ports", methods=["GET"])
@login_required
def ports():
    cfg = config_mod.load()
    check_ports = [cfg["ssh_port"], cfg["ws_port"], cfg["wss_port"], cfg["bridge_port"], cfg["manager_port"]]
    return render_template("ports.html", cfg=cfg, port_status=network.check_ports(check_ports))


@bp.route("/firewall", methods=["GET", "POST"])
@login_required
def firewall_settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "sync":
            firewall.sync_rules(current_admin())
            flash("Firewall rules synced with current configuration.", "success")
        elif action == "enable":
            firewall.enable(current_admin())
            flash("Firewall enabled.", "success")
    return render_template("firewall.html", status=firewall.status())
