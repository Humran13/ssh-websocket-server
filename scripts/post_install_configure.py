#!/usr/bin/env python3
"""Run by install.sh (as root) after packages/venv/systemd units are in
place. Reuses the exact same manager/core modules the web panel and CLI
use, so install-time behavior (config validation, Nginx rendering,
firewall rules, certificate issuance) can never drift from what the panel
does later. Talks to install.sh purely via a single JSON object on stdout
so the shell side stays simple.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "manager"))

from core import auth, config as config_mod, db, domain, firewall, health, network, privileged, secret_key  # noqa: E402,E501


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ssh-port", type=int, required=True)
    p.add_argument("--ws-port", type=int, required=True)
    p.add_argument("--wss-port", type=int, required=True)
    p.add_argument("--bridge-port", type=int, required=True)
    p.add_argument("--manager-port", type=int, required=True)
    p.add_argument("--ws-path", action="append", required=True)
    p.add_argument("--domain", default="")
    p.add_argument("--ws-enabled", choices=["true", "false"], default="true")
    p.add_argument("--enable-firewall", choices=["true", "false"], default="false")
    p.add_argument("--issue-cert", choices=["true", "false"], default="false")
    p.add_argument("--cert-email", default="")
    p.add_argument("--admin-username", default="")
    p.add_argument("--admin-password", default="")
    args = p.parse_args()

    report: dict = {"steps": []}

    def step(name, fn):
        try:
            result = fn()
            report["steps"].append({"name": name, "ok": True, "detail": result})
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            report["steps"].append({"name": name, "ok": False, "detail": str(exc)})

    cfg = config_mod.DEFAULTS.copy()
    cfg.update({
        "ssh_port": args.ssh_port,
        "ws_port": args.ws_port,
        "wss_port": args.wss_port,
        "bridge_port": args.bridge_port,
        "manager_port": args.manager_port,
        "ws_paths": args.ws_path,
        "domain": args.domain or None,
        "install_mode": "domain" if args.domain else "ip",
        "ws_enabled": args.ws_enabled == "true",
        "wss_enabled": False,  # only turned on after a cert exists, below
    })

    def do_save_config():
        config_mod.save(cfg)
        return "config.json written"
    step("save_config", do_save_config)

    def do_init_db():
        db.init_db()
        return "database initialized"
    step("init_db", do_init_db)

    def do_secret_key():
        # Created here, once, as a single process, specifically so that
        # gunicorn's multiple worker processes (see systemd/sshws-manager
        # .service: `-w 2`) never race to generate it independently --
        # see core/secret_key.py for why that race matters.
        secret_key.ensure()
        return "session secret key ready"
    step("secret_key", do_secret_key)

    if args.admin_username and args.admin_password:
        def do_create_admin():
            if not auth.has_any_admin():
                auth.create_admin(args.admin_username, args.admin_password)
                return f"admin '{args.admin_username}' created"
            return "admin already exists, skipped"
        step("create_admin", do_create_admin)

    def do_nginx():
        # Goes through the same privileged action the panel/CLI use later
        # (this process happens to already be root, so it's the in-process
        # fast path -- see core/privileged.py) rather than writing the
        # file directly, so there is exactly one code path that ever
        # writes this file and exactly one that ever needs to be correct.
        rendered = network.render_nginx_config(cfg)
        return privileged.call("nginx_write_site", {"content": rendered})
    step("write_nginx_config", do_nginx)

    if args.domain and args.issue_cert == "true":
        def do_cert():
            result = domain.issue_certificate(args.cert_email or None, actor="installer")
            return result.get("output", "")
        step("issue_certificate", do_cert)

    if args.enable_firewall == "true":
        def do_firewall():
            return firewall.enable(actor="installer")
        step("enable_firewall", do_firewall)
    else:
        def do_firewall_sync():
            return firewall.sync_rules(actor="installer")
        step("sync_firewall_rules", do_firewall_sync)

    def do_health():
        return health.run_all()
    step("health_check", do_health)

    print(json.dumps(report, indent=2))
    return 0 if all(s["ok"] for s in report["steps"]) else 1


if __name__ == "__main__":
    sys.exit(main())
