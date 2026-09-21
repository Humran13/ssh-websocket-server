"""Read/write of /etc/ssh-websocket-server/config.json.

The file is the single source of truth for ports, WebSocket paths, and
domain/SSL state. Both install.sh (via a tiny inline python -c call) and
the Flask app / CLI read and write it through this module so there is one
schema and one validation path.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any

from . import paths

DEFAULTS: dict[str, Any] = {
    "version": "0.1.0",
    "install_mode": "ip",          # "ip" or "domain"
    "domain": None,
    "ssh_port": 22,
    "ws_enabled": True,
    "ws_port": 80,
    "wss_enabled": False,
    "wss_port": 443,
    "ws_paths": ["/ssh"],
    "bridge_bind": "127.0.0.1",
    "bridge_port": 8765,
    "manager_bind": "0.0.0.0",  # noqa: S104 - intentional: the panel must be reachable externally
    "manager_port": 8088,
    "manager_path": "/panel",
    "ssl_cert_path": None,
    "ssl_key_path": None,
    "ssl_provider": None,          # "letsencrypt" or "manual" or None
    "firewall_managed": False,
    "fail2ban_managed": False,
}

REQUIRED_KEYS = set(DEFAULTS.keys())


class ConfigError(ValueError):
    pass


def load() -> dict[str, Any]:
    if not paths.CONFIG_FILE.exists():
        return copy.deepcopy(DEFAULTS)
    with open(paths.CONFIG_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    merged = copy.deepcopy(DEFAULTS)
    merged.update(data)
    return merged


def save(cfg: dict[str, Any]) -> None:
    validate(cfg)
    paths.ensure_dirs()
    paths.ETC_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".config.", suffix=".json", dir=str(paths.ETC_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, paths.CONFIG_FILE)
        try:
            os.chmod(paths.CONFIG_FILE, 0o640)
        except OSError:
            pass
        # save() can run as root (the installer, update.sh, or `ssh-ws`
        # itself) as well as unprivileged (the web panel) -- a file root
        # creates is root-owned regardless of who owns ETC_DIR, and the
        # manager (always unprivileged) needs to read this back at every
        # boot. Verified directly as the root cause of a real startup
        # PermissionError once (for the sibling secret-key file; this
        # file writes exactly the same way).
        paths.chown_to_service_user(paths.CONFIG_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def validate(cfg: dict[str, Any]) -> None:
    missing = REQUIRED_KEYS - set(cfg.keys())
    if missing:
        raise ConfigError(f"config missing required keys: {sorted(missing)}")

    for key in ("ssh_port", "ws_port", "wss_port", "bridge_port", "manager_port"):
        _validate_port(key, cfg[key])

    all_ports = [cfg["ssh_port"], cfg["bridge_port"], cfg["manager_port"]]
    if cfg["ws_enabled"]:
        all_ports.append(cfg["ws_port"])
    if cfg["wss_enabled"]:
        all_ports.append(cfg["wss_port"])
    if len(all_ports) != len(set(all_ports)):
        raise ConfigError("port conflict: ssh_port, ws_port, wss_port, bridge_port and "
                           "manager_port must all be distinct")

    if not cfg["ws_paths"]:
        raise ConfigError("at least one WebSocket path is required")
    for p in cfg["ws_paths"]:
        validate_ws_path(p)
        if p.rstrip("/") == cfg["manager_path"].rstrip("/"):
            raise ConfigError(f"WebSocket path {p!r} conflicts with the manager panel path")

    # Not currently changeable through any UI/CLI action, but validated
    # for the same reason every other field here is: it is interpolated
    # directly into the generated Nginx config (network.py), so it must
    # never be allowed to hold anything that isn't a safe URL path
    # segment even if a future feature exposes it for editing.
    validate_ws_path(cfg["manager_path"])

    if cfg["install_mode"] not in ("ip", "domain"):
        raise ConfigError("install_mode must be 'ip' or 'domain'")
    if cfg["install_mode"] == "domain" and not cfg["domain"]:
        raise ConfigError("install_mode is 'domain' but no domain is configured")
    if cfg["domain"]:
        validate_domain(cfg["domain"])


def _validate_port(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"{name} must be an integer")
    if not (1 <= value <= 65535):
        raise ConfigError(f"{name} must be between 1 and 65535")
    if value < 1024 and name not in ("ssh_port", "ws_port", "wss_port"):
        raise ConfigError(f"{name} may not use a privileged port (<1024)")


def validate_ws_path(p: str) -> str:
    if not isinstance(p, str) or not p:
        raise ConfigError("WebSocket path must be a non-empty string")
    if not p.startswith("/"):
        raise ConfigError("WebSocket path must start with '/'")
    if ".." in p or "//" in p:
        raise ConfigError("WebSocket path may not contain '..' or '//'")
    import re
    if not re.fullmatch(r"/[a-zA-Z0-9._~/-]{1,127}", p):
        raise ConfigError("WebSocket path contains invalid characters")
    return p


def validate_domain(domain: str) -> str:
    import re
    if not isinstance(domain, str) or not domain:
        raise ConfigError("domain must be a non-empty string")
    if len(domain) > 253:
        raise ConfigError("domain is too long")
    label = r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    pattern = rf"^{label}(\.{label})+$"
    if not re.fullmatch(pattern, domain):
        raise ConfigError(f"'{domain}' is not a valid domain name")
    return domain
