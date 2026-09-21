"""UFW helpers. The golden rule: the current SSH port is always allowed
*before* enabling the firewall, and enabling never happens as a side
effect of any other action -- only an explicit, deliberate call.
"""
from __future__ import annotations

from . import config as config_mod
from . import db, privileged


def sync_rules(actor: str = "system") -> dict:
    """Allow every port this install actually needs. Safe to call
    repeatedly (ufw allow is idempotent)."""
    cfg = config_mod.load()
    ports = [cfg["ssh_port"], cfg["manager_port"]]
    if cfg["ws_enabled"]:
        ports.append(cfg["ws_port"])
    if cfg["wss_enabled"]:
        ports.append(cfg["wss_port"])

    allowed = []
    for port in sorted(set(ports)):
        privileged.call("ufw_allow", {"port": port, "proto": "tcp"})
        allowed.append(port)

    db.log_action(actor, "firewall_sync", None, ",".join(map(str, allowed)), success=True)
    return {"allowed_ports": allowed}


def enable(actor: str = "system") -> dict:
    """Only ever call after sync_rules() has run in this same operation --
    install.sh and the panel both call sync_rules() immediately before
    this, so the active SSH port is guaranteed to already be allowed."""
    sync_rules(actor)
    privileged.call("ufw_enable", {})
    cfg = config_mod.load()
    cfg["firewall_managed"] = True
    config_mod.save(cfg)
    db.log_action(actor, "firewall_enable", None, None, success=True)
    return status()


def status() -> dict:
    try:
        data = privileged.call("ufw_status", {})
        output = data.get("output", "")
    except privileged.PrivilegedActionError as exc:
        return {"active": False, "output": str(exc)}
    return {"active": "Status: active" in output, "output": output}
