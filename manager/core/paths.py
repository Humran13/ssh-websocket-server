"""Filesystem locations used by the project.

Every path is resolvable through an environment variable override so the
test suite (and local development on a non-Linux machine) can point the
whole application at a throwaway directory instead of real system paths.
Production installs never set these -- install.sh writes /etc, /var/lib,
/var/log, /opt paths as normal.

Values are computed on every access (via module ``__getattr__``, PEP 562)
rather than cached at import time, so tests can flip SSHWS_* env vars with
monkeypatch between cases without needing to reload this module or any of
its importers.
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULTS = {
    "SSHWS_ETC": "/etc/ssh-websocket-server",
    "SSHWS_VAR": "/var/lib/ssh-websocket-server",
    "SSHWS_LOG": "/var/log/ssh-websocket-server",
    "SSHWS_ROOT": "/opt/ssh-websocket-server",
    "SSHWS_NGINX_SITE": "/etc/nginx/sites-available/ssh-websocket-server.conf",
    "SSHWS_NGINX_LINK": "/etc/nginx/sites-enabled/ssh-websocket-server.conf",
    "SSHWS_PAM_LIMITS": "/etc/security/limits.d/90-ssh-websocket-server.conf",
    "SSHWS_SUDOERS": "/etc/sudoers.d/ssh-websocket-server",
}


def _env_path(var: str) -> Path:
    return Path(os.environ.get(var, _DEFAULTS[var]))


def __getattr__(name: str) -> Path | str:  # noqa: N807 - PEP 562 module hook
    if name == "ETC_DIR":
        return _env_path("SSHWS_ETC")
    if name == "VAR_DIR":
        return _env_path("SSHWS_VAR")
    if name == "LOG_DIR":
        return _env_path("SSHWS_LOG")
    if name == "INSTALL_ROOT":
        return _env_path("SSHWS_ROOT")
    if name == "BACKUP_DIR":
        return Path(os.environ.get("SSHWS_BACKUP_DIR", str(_env_path("SSHWS_VAR") / "backups")))
    if name == "CONFIG_FILE":
        return _env_path("SSHWS_ETC") / "config.json"
    if name == "DB_FILE":
        return _env_path("SSHWS_VAR") / "manager.db"
    if name == "NGINX_SITE_FILE":
        return _env_path("SSHWS_NGINX_SITE")
    if name == "NGINX_SITE_LINK":
        return _env_path("SSHWS_NGINX_LINK")
    if name == "PAM_LIMITS_FILE":
        return _env_path("SSHWS_PAM_LIMITS")
    if name == "SUDOERS_FILE":
        return _env_path("SSHWS_SUDOERS")
    if name == "PRIV_HELPER":
        return _env_path("SSHWS_ROOT") / "scripts" / "priv_helper.py"
    if name == "SERVICE_USER":
        return os.environ.get("SSHWS_SERVICE_USER", "sshws")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def ensure_dirs() -> None:
    dirs = (__getattr__("ETC_DIR"), __getattr__("VAR_DIR"), __getattr__("LOG_DIR"), __getattr__("BACKUP_DIR"))
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def chown_to_service_user(path) -> None:
    """No-op unless running as root. A file root creates always defaults
    to root:root ownership regardless of which user owns its parent
    directory -- so any code path that writes into ETC_DIR/VAR_DIR while
    running as root (the installer, `update.sh`, or `ssh-ws` itself, all
    of which run as root) must call this afterward, or the manager
    (always running as SERVICE_USER) will hit a PermissionError reading
    it back. Verified directly: this is exactly the bug the first two
    callers of this function were added to fix.
    """
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    try:
        import pwd
        pw = pwd.getpwnam(__getattr__("SERVICE_USER"))
        os.chown(str(path), pw.pw_uid, pw.pw_gid)
    except (KeyError, ImportError, OSError):
        pass  # service account not present yet (e.g. local dev) -- leave as-is
