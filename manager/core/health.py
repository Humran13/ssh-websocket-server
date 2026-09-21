"""Health checks run by install.sh after setup, and available from the
panel/CLI at any time.
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.request

from . import config as config_mod
from . import db, privileged


def check_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_http_upgrade(host: str, port: int, path: str, timeout: float = 3.0) -> bool:
    """Confirms the WebSocket endpoint answers a websocket handshake request
    with 101 Switching Protocols (a plain GET would just be proxied to the
    bridge, which only speaks the WebSocket protocol)."""
    try:
        req = urllib.request.Request(
            f"http://{host}:{port}{path}",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            },
        )
        urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 - fixed localhost URL
        return True
    except urllib.error.HTTPError as exc:
        return exc.code == 101
    except (urllib.error.URLError, OSError):
        return False


def run_all() -> dict[str, dict]:
    cfg = config_mod.load()
    results: dict[str, dict] = {}

    results["sshd"] = {"ok": check_tcp("127.0.0.1", cfg["ssh_port"])}
    results["bridge"] = {"ok": check_tcp(cfg["bridge_bind"], cfg["bridge_port"])}

    if cfg["ws_enabled"]:
        path = cfg["ws_paths"][0]
        results["ws_endpoint"] = {"ok": check_http_upgrade("127.0.0.1", cfg["ws_port"], path)}

    try:
        nginx_result = privileged.call("nginx_test", {})
        results["nginx_config"] = {"ok": nginx_result.get("ok", False), "detail": nginx_result.get("output")}
    except privileged.PrivilegedActionError as exc:
        results["nginx_config"] = {"ok": False, "detail": str(exc)}

    results["manager"] = {"ok": check_tcp("127.0.0.1", cfg["manager_port"])}

    try:
        with db.cursor() as cur:
            cur.execute("SELECT 1")
        results["database"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        results["database"] = {"ok": False, "detail": str(exc)}

    for svc in ("ssh", "nginx", "sshws-bridge", "sshws-manager"):
        try:
            status = privileged.call("service_status", {"name": svc}).get("status")
            results[f"service:{svc}"] = {"ok": status == "active", "detail": status}
        except privileged.PrivilegedActionError as exc:
            results[f"service:{svc}"] = {"ok": False, "detail": str(exc)}

    return results
