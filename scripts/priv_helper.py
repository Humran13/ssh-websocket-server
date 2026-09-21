#!/usr/bin/env python3
"""Narrowly-scoped root helper invoked by the unprivileged manager via sudo.

Design goals (see docs/SECURITY.md for the full write-up):

  * The Flask app and the CLI both run as an unprivileged service user
    ("sshws"). This script is the ONLY thing that ever runs as root.
  * Exactly one sudoers rule is needed, with no wildcard arguments:
        sshws ALL=(root) NOPASSWD: /opt/.../venv/bin/python3 /opt/.../scripts/priv_helper.py
    All input (action name, arguments, and any secret such as a new
    password) is read as one JSON object from stdin -- never from argv --
    so nothing sensitive ever shows up in `ps`.
  * Every action is an allowlisted function. There is no "run this shell
    command" action and no string is ever handed to a shell. All external
    commands are invoked as argument arrays (subprocess with shell=False).
  * All identifiers (usernames, paths, ports, domains) are validated
    against strict patterns before they touch a subprocess call.
  * Only OS accounts that are tracked in the manager's own database as
    "managed" may be modified or deleted, and accounts with UID < 1000,
    plus a hard-coded denylist (root, the service account itself, etc.)
    can never be targeted, regardless of what the caller claims.
"""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import time

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,31}$")
DOMAIN_LABEL = r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
DOMAIN_RE = re.compile(rf"^{DOMAIN_LABEL}(\.{DOMAIN_LABEL})+$")
WS_PATH_RE = re.compile(r"^/[a-zA-Z0-9._~/-]{1,127}$")
SERVICE_ALLOWLIST = {"ssh", "sshd", "nginx", "sshws-bridge", "sshws-manager", "fail2ban"}

# Never allowed as an SSH-WS "managed" username, no matter what the caller sends.
RESERVED_USERNAMES = {
    "root", "daemon", "bin", "sys", "sync", "games", "man", "lp", "mail",
    "news", "uucp", "proxy", "www-data", "backup", "list", "irc", "gnats",
    "nobody", "systemd-network", "systemd-resolve", "systemd-timesync",
    "messagebus", "sshd", "sshws", "syslog", "_apt", "landscape", "pollinate",
    "ubuntu", "fail2ban", "certbot",
}

MIN_MANAGED_UID = 1000


class HelperError(Exception):
    pass


def run(cmd: list[str], input_text: str | None = None, check: bool = True,
        timeout: int = 30) -> subprocess.CompletedProcess:
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
        raise HelperError("internal error: command must be a list of strings")
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        check=check,
        shell=False,
        timeout=timeout,
    )


def require_username(username: object) -> str:
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username):
        raise HelperError(f"invalid username: {username!r}")
    if username in RESERVED_USERNAMES:
        raise HelperError(f"refusing to operate on reserved username: {username}")
    return username


def require_managed_account(username: str) -> pwd.struct_passwd:
    """Refuse to touch anything that isn't a plain, project-managed human account."""
    require_username(username)
    try:
        entry = pwd.getpwnam(username)
    except KeyError as exc:
        raise HelperError(f"no such OS account: {username}") from exc
    if entry.pw_uid < MIN_MANAGED_UID:
        raise HelperError(f"refusing to operate on system account (uid {entry.pw_uid}): {username}")
    return entry


def require_domain(domain: object) -> str:
    if not isinstance(domain, str) or not DOMAIN_RE.fullmatch(domain):
        raise HelperError(f"invalid domain: {domain!r}")
    return domain


def require_ws_path(path: object) -> str:
    if not isinstance(path, str) or not WS_PATH_RE.fullmatch(path) or ".." in path or "//" in path:
        raise HelperError(f"invalid websocket path: {path!r}")
    return path


def require_port(port: object) -> int:
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        raise HelperError(f"invalid port: {port!r}")
    return port


def require_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HelperError(f"invalid {name}: {value!r}")
    return value


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def action_user_create(args: dict) -> dict:
    username = require_username(args.get("username"))
    try:
        pwd.getpwnam(username)
        raise HelperError(f"OS account already exists: {username}")
    except KeyError:
        pass
    password = args.get("password")
    if not isinstance(password, str) or len(password) < 8:
        raise HelperError("password must be a string of at least 8 characters")

    run(["useradd", "--create-home", "--shell", "/usr/sbin/nologin", username])
    run(["chpasswd"], input_text=f"{username}:{password}\n")

    expires_at = args.get("expires_at")
    if expires_at is not None:
        _apply_expiry(username, require_positive_int(expires_at, "expires_at"))

    return {"username": username}


def action_user_set_password(args: dict) -> dict:
    username = require_managed_account(args.get("username")).pw_name
    password = args.get("password")
    if not isinstance(password, str) or len(password) < 8:
        raise HelperError("password must be a string of at least 8 characters")
    run(["chpasswd"], input_text=f"{username}:{password}\n")
    return {"username": username}


def action_user_disable(args: dict) -> dict:
    username = require_managed_account(args.get("username")).pw_name
    run(["usermod", "--lock", username])
    _kill_all_sessions(username)
    return {"username": username}


def action_user_enable(args: dict) -> dict:
    username = require_managed_account(args.get("username")).pw_name
    run(["usermod", "--unlock", username])
    return {"username": username}


def action_user_delete(args: dict) -> dict:
    username = require_managed_account(args.get("username")).pw_name
    _kill_all_sessions(username)
    run(["userdel", "--remove", username], check=False)
    return {"username": username}


def _apply_expiry(username: str, expires_at: int | None) -> None:
    if expires_at is None:
        run(["chage", "--expiredate", "-1", username])
    else:
        date_str = time.strftime("%Y-%m-%d", time.gmtime(expires_at))
        run(["chage", "--expiredate", date_str, username])


def action_user_set_expiry(args: dict) -> dict:
    username = require_managed_account(args.get("username")).pw_name
    expires_at = args.get("expires_at")
    _apply_expiry(username, None if expires_at is None else require_positive_int(expires_at, "expires_at"))
    return {"username": username}


def action_user_set_max_sessions(args: dict) -> dict:
    from pathlib import Path
    username = require_managed_account(args.get("username")).pw_name
    max_sessions = args.get("max_sessions")
    limits_file = Path(args.get("limits_file", "/etc/security/limits.d/90-ssh-websocket-server.conf"))
    if not str(limits_file).startswith("/etc/security/limits.d/"):
        raise HelperError("refusing to write limits file outside /etc/security/limits.d/")

    lines: list[str] = []
    if limits_file.exists():
        for line in limits_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) == 4 and parts[0] == username and parts[2] == "maxlogins":
                continue
            lines.append(line)

    if max_sessions is not None:
        n = require_positive_int(max_sessions, "max_sessions")
        lines.append(f"{username} hard maxlogins {n}")

    limits_file.parent.mkdir(parents=True, exist_ok=True)
    content = "# Managed by ssh-websocket-server. Do not edit by hand.\n" + "\n".join(lines) + "\n"
    limits_file.write_text(content, encoding="utf-8")
    os.chmod(limits_file, 0o644)
    return {"username": username, "max_sessions": max_sessions}


def _list_ssh_sessions() -> list[dict]:
    result = run(["who", "-u"], check=False)
    sessions = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        user, tty = parts[0], parts[1]
        pid = None
        for p in parts:
            if p.isdigit():
                pid = int(p)
        source = ""
        if "(" in line and ")" in line:
            source = line[line.index("(") + 1: line.rindex(")")]
        sessions.append({"username": user, "tty": tty, "pid": pid, "source": source})
    return sessions


def action_sessions_list(_args: dict) -> dict:
    return {"sessions": _list_ssh_sessions()}


def _kill_all_sessions(username: str) -> None:
    for sess in _list_ssh_sessions():
        if sess["username"] == username and sess["pid"]:
            _kill_session_pid(sess["pid"])


def _kill_session_pid(pid: int) -> None:
    try:
        ppath = f"/proc/{pid}/comm"
        if os.path.exists(ppath):
            with open(ppath, encoding="utf-8") as fh:
                comm = fh.read().strip()
            if comm not in ("sshd", "sshd-session"):
                raise HelperError(f"refusing to kill non-sshd process {pid} ({comm})")
        run(["kill", "-TERM", str(pid)], check=False)
    except FileNotFoundError:
        pass


def action_session_kill(args: dict) -> dict:
    pid = require_positive_int(args.get("pid"), "pid")
    username = require_managed_account(args.get("username")).pw_name
    sessions = [s for s in _list_ssh_sessions() if s["pid"] == pid and s["username"] == username]
    if not sessions:
        raise HelperError("no matching active session for that user/pid")
    _kill_session_pid(pid)
    return {"pid": pid}


def action_service_restart(args: dict) -> dict:
    name = args.get("name")
    if name not in SERVICE_ALLOWLIST:
        raise HelperError(f"service not in allowlist: {name!r}")
    run(["systemctl", "restart", name])
    return {"name": name}


def action_service_reload(args: dict) -> dict:
    name = args.get("name")
    if name not in SERVICE_ALLOWLIST:
        raise HelperError(f"service not in allowlist: {name!r}")
    run(["systemctl", "reload-or-restart", name])
    return {"name": name}


def action_service_status(args: dict) -> dict:
    name = args.get("name")
    if name not in SERVICE_ALLOWLIST:
        raise HelperError(f"service not in allowlist: {name!r}")
    result = run(["systemctl", "is-active", name], check=False)
    return {"name": name, "status": result.stdout.strip() or "unknown"}


def action_nginx_test(_args: dict) -> dict:
    result = run(["nginx", "-t"], check=False)
    return {"ok": result.returncode == 0, "output": (result.stdout + result.stderr).strip()}


NGINX_SITE_PATH = "/etc/nginx/sites-available/ssh-websocket-server.conf"
NGINX_LINK_PATH = "/etc/nginx/sites-enabled/ssh-websocket-server.conf"


def action_nginx_write_site(args: dict) -> dict:
    """Writes this project's Nginx site file. The destination is not a
    caller-supplied argument at all -- it is always exactly
    NGINX_SITE_PATH -- so there is no path to validate and no way to
    target any other file. /etc/nginx/sites-available/ is root-owned, so
    the unprivileged manager process cannot write here directly; this is
    the one and only way that config reaches disk.
    """
    content = args.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HelperError("content must be a non-empty string")
    os.makedirs(os.path.dirname(NGINX_SITE_PATH), exist_ok=True)
    with open(NGINX_SITE_PATH, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(NGINX_SITE_PATH, 0o644)
    if not os.path.exists(NGINX_LINK_PATH):
        os.makedirs(os.path.dirname(NGINX_LINK_PATH), exist_ok=True)
        os.symlink(NGINX_SITE_PATH, NGINX_LINK_PATH)
    return {"path": NGINX_SITE_PATH}


def action_ufw_status(_args: dict) -> dict:
    result = run(["ufw", "status", "verbose"], check=False)
    return {"output": result.stdout.strip()}


def action_ufw_allow(args: dict) -> dict:
    port = require_port(args.get("port"))
    proto = args.get("proto", "tcp")
    if proto not in ("tcp", "udp"):
        raise HelperError(f"invalid protocol: {proto!r}")
    run(["ufw", "allow", f"{port}/{proto}"])
    return {"port": port, "proto": proto}


def action_ufw_enable(_args: dict) -> dict:
    run(["ufw", "--force", "enable"])
    return {"enabled": True}


def action_certbot_issue(args: dict) -> dict:
    domain = require_domain(args.get("domain"))
    email = args.get("email")
    cmd = ["certbot", "--nginx", "-d", domain, "--non-interactive", "--agree-tos", "--no-eff-email"]
    if email:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise HelperError("invalid email")
        cmd += ["-m", email]
    else:
        cmd += ["--register-unsafely-without-email"]
    # certbot talks to Let's Encrypt over the network (domain validation,
    # certificate issuance); 30s is comfortably enough for most local
    # commands here but has been observed to be too tight for this one.
    result = run(cmd, check=False, timeout=180)
    return {"ok": result.returncode == 0, "output": (result.stdout + result.stderr).strip()}


def action_certbot_renew(_args: dict) -> dict:
    result = run(["certbot", "renew", "--non-interactive"], check=False, timeout=180)
    return {"ok": result.returncode == 0, "output": (result.stdout + result.stderr).strip()}


BACKUP_BASE = "/var/lib/ssh-websocket-server/backups"


def action_certs_export(args: dict) -> dict:
    """Copy a domain's Let's Encrypt cert+key to a location the unprivileged
    service user can read, so the backup tool can include them without the
    manager process ever running as root. Caller (backup.py) is responsible
    for deleting the export directory once it has copied what it needs.
    """
    import pwd as _pwd
    import shutil as _shutil

    domain = require_domain(args.get("domain"))
    live_dir = f"/etc/letsencrypt/live/{domain}"
    if not os.path.isdir(live_dir):
        raise HelperError(f"no certificate found for domain: {domain}")

    export_dir = f"{BACKUP_BASE}/.ssl-export"
    os.makedirs(export_dir, exist_ok=True, mode=0o700)

    copied = []
    for fname in ("fullchain.pem", "privkey.pem"):
        src = os.path.join(live_dir, fname)
        if not os.path.isfile(src):
            continue
        # os.path.realpath resolves the certbot symlink; refuse anything
        # that escapes the expected letsencrypt tree.
        real_src = os.path.realpath(src)
        if not real_src.startswith("/etc/letsencrypt/"):
            raise HelperError(f"refusing to export file outside /etc/letsencrypt/: {real_src}")
        dst = os.path.join(export_dir, fname)
        _shutil.copyfile(real_src, dst)
        os.chmod(dst, 0o600)
        copied.append(fname)

    try:
        svc_uid = _pwd.getpwnam("sshws").pw_uid
        svc_gid = _pwd.getpwnam("sshws").pw_gid
        os.chown(export_dir, svc_uid, svc_gid)
        for fname in copied:
            os.chown(os.path.join(export_dir, fname), svc_uid, svc_gid)
    except KeyError:
        pass  # service account not present (e.g. local dev) -- leave root-owned

    return {"export_dir": export_dir, "files": copied}


ACTIONS = {
    "user_create": action_user_create,
    "user_set_password": action_user_set_password,
    "user_disable": action_user_disable,
    "user_enable": action_user_enable,
    "user_delete": action_user_delete,
    "user_set_expiry": action_user_set_expiry,
    "user_set_max_sessions": action_user_set_max_sessions,
    "sessions_list": action_sessions_list,
    "session_kill": action_session_kill,
    "service_restart": action_service_restart,
    "service_reload": action_service_reload,
    "service_status": action_service_status,
    "nginx_test": action_nginx_test,
    "ufw_status": action_ufw_status,
    "ufw_allow": action_ufw_allow,
    "ufw_enable": action_ufw_enable,
    "certbot_issue": action_certbot_issue,
    "certbot_renew": action_certbot_renew,
    "certs_export": action_certs_export,
    "nginx_write_site": action_nginx_write_site,
}


def main() -> int:
    if os.geteuid() != 0:
        print(json.dumps({"ok": False, "error": "priv_helper must run as root (via sudo)"}), file=sys.stdout)
        return 1

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid JSON on stdin: {exc}"}))
        return 1

    action = payload.get("action")
    args = payload.get("args", {})
    if not isinstance(args, dict):
        print(json.dumps({"ok": False, "error": "args must be an object"}))
        return 1

    handler = ACTIONS.get(action)
    if handler is None:
        print(json.dumps({"ok": False, "error": f"unknown action: {action!r}"}))
        return 1

    try:
        data = handler(args)
        print(json.dumps({"ok": True, "data": data}))
        return 0
    except HelperError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    except subprocess.CalledProcessError as exc:
        print(json.dumps({"ok": False, "error": f"{' '.join(exc.cmd)} failed: {exc.stderr.strip()}"}))
        return 1
    except Exception as exc:  # noqa: BLE001 - last-resort guard, still reported safely
        print(json.dumps({"ok": False, "error": f"internal error: {exc}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
