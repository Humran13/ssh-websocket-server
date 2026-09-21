#!/usr/bin/env python3
"""Interactive `ssh-ws` CLI. Installed as /usr/local/bin/ssh-ws (a thin
sudo-wrapping shell script -- see scripts/install_cli.sh) so it always
runs as root, exactly like a human administrator running any other admin
tool on the box. It calls the exact same manager/core functions the web
panel uses -- see manager/core/*.py for the actual business logic; this
file is presentation only.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "manager"))

from core import (auth, backup, config as config_mod, db, domain,  # noqa: E402
                   firewall, health, logs, system_info, users, version, ws_settings)

ACTOR = f"cli:{os.environ.get('SUDO_USER', os.environ.get('USER', 'root'))}"


def _pause():
    input("\nPress Enter to continue...")


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def _ask_yes_no(prompt: str, default_yes: bool = False) -> bool:
    hint = "Y/n" if default_yes else "y/N"
    value = input(f"{prompt} [{hint}]: ").strip().lower()
    if not value:
        return default_yes
    return value in ("y", "yes")


def menu_dashboard():
    cfg = config_mod.load()
    print(f"\nHostname:        {system_info.hostname()}")
    print(f"Public IP:       {system_info.public_ip() or 'unknown'}")
    print(f"OS:              {system_info.os_release().get('PRETTY_NAME', 'unknown')}")
    print(f"Kernel:          {system_info.kernel()}")
    up = system_info.uptime_seconds()
    print(f"Uptime:          {int(up // 3600)}h {int((up % 3600) // 60)}m" if up else "Uptime: unknown")
    print(f"CPU:             {system_info.cpu_percent()}%")
    mem = system_info.memory_usage()
    if mem:
        print(f"Memory:          {mem['used'] // 1048576} / {mem['total'] // 1048576} MB")
    disk = system_info.disk_usage("/")
    print(f"Disk (/):        {disk['used'] // 1073741824} / {disk['total'] // 1073741824} GB")
    print(f"Installed ver.:  v{version.installed_version()}")
    print()
    print(f"sshd:            {system_info.service_status('ssh')}")
    print(f"bridge:          {system_info.service_status('sshws-bridge')}")
    print(f"nginx:           {system_info.service_status('nginx')}")
    print(f"manager:         {system_info.service_status('sshws-manager')}")
    print(f"firewall:        {system_info.firewall_status()}")
    print()
    print(f"Domain:          {cfg['domain'] or '(none -- IP mode)'}")
    print(f"SSH port:        {cfg['ssh_port']}")
    print(f"WS:              {'enabled, port ' + str(cfg['ws_port']) if cfg['ws_enabled'] else 'disabled'}")
    print(f"WSS:             {'enabled, port ' + str(cfg['wss_port']) if cfg['wss_enabled'] else 'disabled'}")
    print(f"WS path(s):      {', '.join(cfg['ws_paths'])}")
    print(f"Managed users:   {len(users.list_users())}")


def menu_add_user():
    username = _ask("Username")
    try:
        users.validate_username(username)
    except users.UserError as exc:
        print(f"Error: {exc}")
        return
    password = _ask("Password (blank = auto-generate)") or users.generate_password()
    expiry_days = _ask("Expiry in days (blank = never)")
    max_sessions = _ask("Max concurrent sessions (blank = unlimited)")
    try:
        expires_at = int(time.time()) + int(expiry_days) * 86400 if expiry_days else None
        u = users.create_user(username, password, ACTOR, expires_at=expires_at,
                               max_sessions=int(max_sessions) if max_sessions else None)
        print(f"\nCreated '{u.username}'. Password: {password}  (shown once -- store it now)")
    except (users.UserError, ValueError) as exc:
        print(f"Error: {exc}")


def menu_list_users():
    rows = users.list_users()
    if not rows:
        print("No managed users yet.")
        return
    print(f"{'USERNAME':<20}{'STATUS':<12}{'EXPIRES':<22}{'MAX SESSIONS'}")
    for u in rows:
        status = "disabled" if not u.enabled else ("expired" if u.expired else "active")
        expires = time.strftime("%Y-%m-%d", time.gmtime(u.expires_at)) if u.expires_at else "never"
        print(f"{u.username:<20}{status:<12}{expires:<22}{u.max_sessions or 'unlimited'}")


def menu_change_password():
    username = _ask("Username")
    password = _ask("New password (blank = auto-generate)") or users.generate_password()
    try:
        users.set_password(username, password, ACTOR)
        print(f"Password for '{username}' set to: {password}")
    except users.UserError as exc:
        print(f"Error: {exc}")


def menu_extend_expiry():
    username = _ask("Username")
    days = _ask("Extend by how many days", "30")
    try:
        users.extend_expiry(username, int(days) * 86400, ACTOR)
        print("Done.")
    except (users.UserError, ValueError) as exc:
        print(f"Error: {exc}")


def menu_disable_user():
    username = _ask("Username")
    try:
        users.disable_user(username, ACTOR)
        print("Done.")
    except users.UserError as exc:
        print(f"Error: {exc}")


def menu_enable_user():
    username = _ask("Username")
    try:
        users.enable_user(username, ACTOR)
        print("Done.")
    except users.UserError as exc:
        print(f"Error: {exc}")


def menu_delete_user():
    username = _ask("Username")
    confirm_name = _ask(f"Type '{username}' again to confirm deletion")
    try:
        users.delete_user(username, ACTOR, confirm=(confirm_name == username))
        print("Deleted.")
    except users.UserError as exc:
        print(f"Error: {exc}")


def menu_active_connections():
    sessions = users.list_active_sessions()
    if not sessions:
        print("No active sessions for managed users.")
        return
    for s in sessions:
        print(f"{s['username']:<16}{s['tty']:<12}{s['source'] or '-':<20}pid={s['pid']}")


def menu_disconnect():
    username = _ask("Username")
    pid = _ask("PID (see 'Active Connections')")
    try:
        users.disconnect_session(username, int(pid), ACTOR)
        print("Disconnected.")
    except (users.UserError, ValueError) as exc:
        print(f"Error: {exc}")


def menu_ws_settings():
    cfg = config_mod.load()
    print(f"Current: ws={cfg['ws_enabled']} (port {cfg['ws_port']}), "
          f"wss={cfg['wss_enabled']} (port {cfg['wss_port']}), paths={cfg['ws_paths']}")
    if _ask_yes_no("Change WebSocket paths?"):
        raw = _ask("Comma-separated paths", ",".join(cfg["ws_paths"]))
        try:
            ws_settings.update_paths([p.strip() for p in raw.split(",") if p.strip()], ACTOR)
            print("Updated.")
        except ws_settings.WsSettingsError as exc:
            print(f"Error: {exc}")
    if _ask_yes_no("Toggle WS enabled?"):
        try:
            ws_settings.set_enabled(not cfg["ws_enabled"], None, ACTOR)
        except ws_settings.WsSettingsError as exc:
            print(f"Error: {exc}")
    if _ask_yes_no("Toggle WSS enabled?"):
        try:
            ws_settings.set_enabled(None, not cfg["wss_enabled"], ACTOR)
        except ws_settings.WsSettingsError as exc:
            print(f"Error: {exc}")


def menu_domain_ssl():
    cfg = config_mod.load()
    print(f"Current domain: {cfg['domain'] or '(none)'}")
    if _ask_yes_no("Set/change domain?"):
        new_domain = _ask("Domain")
        try:
            result = domain.set_domain(new_domain, ACTOR)
            print(f"DNS check: {result}")
        except (domain.DomainError, config_mod.ConfigError) as exc:
            print(f"Error: {exc}")
            return
        if _ask_yes_no("Request Let's Encrypt certificate now?", default_yes=True):
            email = _ask("Contact email (blank = none)")
            try:
                domain.issue_certificate(email or None, ACTOR)
                print("Certificate issued; WSS enabled.")
            except domain.DomainError as exc:
                print(f"Error: {exc}")
    elif cfg["domain"] and _ask_yes_no("Remove domain (switch to IP mode)?"):
        domain.remove_domain(ACTOR)
        print("Done.")


def menu_port_settings():
    cfg = config_mod.load()
    print(f"ssh={cfg['ssh_port']} ws={cfg['ws_port']} wss={cfg['wss_port']} "
          f"bridge={cfg['bridge_port']} manager={cfg['manager_port']}")
    if not _ask_yes_no("Change WS/WSS/bridge ports?"):
        return
    ws_port = _ask("WS port", str(cfg["ws_port"]))
    wss_port = _ask("WSS port", str(cfg["wss_port"]))
    bridge_port = _ask("Bridge port", str(cfg["bridge_port"]))
    try:
        ws_settings.update_ports(int(ws_port), int(wss_port), int(bridge_port), ACTOR)
        print("Updated.")
    except (ws_settings.WsSettingsError, ValueError) as exc:
        print(f"Error: {exc}")


def menu_firewall():
    print(firewall.status()["output"])
    if _ask_yes_no("Sync firewall rules with current config?"):
        firewall.sync_rules(ACTOR)
        print("Synced.")
    if _ask_yes_no("Enable UFW now?"):
        firewall.enable(ACTOR)
        print("Enabled.")


def menu_logs():
    source = _ask(f"Source ({', '.join(logs.available_sources())})", "manager")
    try:
        for line in logs.tail(source, 100):
            print(line)
    except ValueError as exc:
        print(f"Error: {exc}")


def menu_backup():
    include_ssl = _ask_yes_no("Include SSL private key?")
    path = backup.create_backup(include_ssl=include_ssl, actor=ACTOR)
    print(f"Backup created: {path}")


def menu_restore():
    existing = backup.list_backups()
    if not existing:
        print("No backups available.")
        return
    for i, b in enumerate(existing):
        print(f"{i}: {b.name}")
    idx = _ask("Backup number to restore")
    try:
        chosen = existing[int(idx)]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return
    if not _ask_yes_no(f"Restore from {chosen.name}? A safety backup is taken first.", default_yes=False):
        return
    try:
        result = backup.restore_backup(chosen)
        print(f"Restored. Safety backup: {result['safety_backup']}")
    except backup.BackupError as exc:
        print(f"Error: {exc}")


def menu_update():
    import subprocess
    script = Path(__file__).resolve().parents[1] / "update.sh"
    subprocess.run(["bash", str(script)], check=False)


def menu_restart_services():
    from core import privileged
    for name in ("nginx", "sshws-bridge", "sshws-manager"):
        try:
            privileged.call("service_restart", {"name": name})
            print(f"Restarted {name}.")
        except privileged.PrivilegedActionError as exc:
            print(f"Error restarting {name}: {exc}")


def menu_uninstall():
    import subprocess
    script = Path(__file__).resolve().parents[1] / "uninstall.sh"
    subprocess.run(["bash", str(script)], check=False)


def menu_health():
    for name, r in health.run_all().items():
        print(f"{name:<20} {'OK' if r['ok'] else 'FAIL':<6} {r.get('detail') or ''}")


MENU = [
    ("Dashboard / Server Status", menu_dashboard),
    ("Add SSH User", menu_add_user),
    ("List SSH Users", menu_list_users),
    ("Change User Password", menu_change_password),
    ("Extend User Expiry", menu_extend_expiry),
    ("Disable User", menu_disable_user),
    ("Enable User", menu_enable_user),
    ("Delete User", menu_delete_user),
    ("Active Connections", menu_active_connections),
    ("Disconnect User", menu_disconnect),
    ("WebSocket Settings", menu_ws_settings),
    ("Domain / SSL", menu_domain_ssl),
    ("Port Settings", menu_port_settings),
    ("Firewall Status", menu_firewall),
    ("View Logs", menu_logs),
    ("Backup", menu_backup),
    ("Restore", menu_restore),
    ("Update", menu_update),
    ("Restart Services", menu_restart_services),
    ("Uninstall", menu_uninstall),
    ("Health Checks", menu_health),
]


def main() -> int:
    db.init_db()
    if not auth.has_any_admin():
        print("No web panel admin exists yet. You can create one from here.")
        if _ask_yes_no("Create the initial panel admin now?", default_yes=True):
            uname = _ask("Admin username", "admin")
            import getpass
            pw = getpass.getpass("Admin password (12+ chars): ")
            try:
                auth.create_admin(uname, pw)
                print("Admin created.")
            except auth.AuthError as exc:
                print(f"Error: {exc}")

    while True:
        print("\nSSH WebSocket Server Manager\n")
        for i, (label, _fn) in enumerate(MENU, start=1):
            print(f"{i:>2}. {label}")
        print(" 0. Exit\n")
        choice = input("Select an option: ").strip()
        if choice == "0":
            return 0
        try:
            idx = int(choice) - 1
            if idx < 0:
                raise ValueError
            _label, fn = MENU[idx]
        except (ValueError, IndexError):
            print("Invalid selection.")
            continue
        try:
            fn()
        except KeyboardInterrupt:
            print()
        except Exception as exc:  # noqa: BLE001 - CLI must never hard-crash the whole menu
            print(f"Unexpected error: {exc}")
        _pause()


if __name__ == "__main__":
    sys.exit(main())
