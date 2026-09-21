"""WebSocket configuration changes: enable/disable WS/WSS, paths, ports.

Every change is written to config.json, then re-rendered into Nginx and
reloaded, with the same backup-before-apply / rollback-on-failure pattern
used by domain.py.
"""
from __future__ import annotations

from . import config as config_mod
from . import db, domain, network, privileged


class WsSettingsError(ValueError):
    pass


def _apply(cfg: dict) -> None:
    config_mod.save(cfg)
    domain._apply_nginx(cfg)  # noqa: SLF001 - intentional reuse of the shared apply/rollback logic


def update_paths(ws_paths: list[str], actor: str) -> dict:
    cfg = config_mod.load()
    cleaned = []
    for p in ws_paths:
        p = config_mod.validate_ws_path(p)
        if p not in cleaned:
            cleaned.append(p)
    if not cleaned:
        raise WsSettingsError("at least one WebSocket path is required")
    cfg["ws_paths"] = cleaned
    _apply(cfg)
    db.log_action(actor, "ws_paths_update", None, ",".join(cleaned), success=True)
    return cfg


def set_enabled(ws_enabled: bool | None, wss_enabled: bool | None, actor: str) -> dict:
    cfg = config_mod.load()
    if ws_enabled is not None:
        cfg["ws_enabled"] = bool(ws_enabled)
    if wss_enabled is not None:
        if wss_enabled and not (cfg["ssl_cert_path"] and cfg["ssl_key_path"]):
            raise WsSettingsError("cannot enable WSS before a certificate is issued")
        cfg["wss_enabled"] = bool(wss_enabled)
    if not cfg["ws_enabled"] and not cfg["wss_enabled"]:
        raise WsSettingsError("at least one of WS or WSS must remain enabled")
    _apply(cfg)
    db.log_action(actor, "ws_enabled_update", None,
                  f"ws={cfg['ws_enabled']} wss={cfg['wss_enabled']}", success=True)
    return cfg


def update_ports(ws_port: int | None, wss_port: int | None, bridge_port: int | None, actor: str) -> dict:
    cfg = config_mod.load()
    if ws_port is not None:
        cfg["ws_port"] = ws_port
    if wss_port is not None:
        cfg["wss_port"] = wss_port
    if bridge_port is not None:
        cfg["bridge_port"] = bridge_port
    try:
        config_mod.validate(cfg)
    except config_mod.ConfigError as exc:
        raise WsSettingsError(str(exc)) from exc

    for port in filter(None, [ws_port, wss_port]):
        if not network.is_port_free(port) and port not in (
                config_mod.load()["ws_port"], config_mod.load()["wss_port"]):
            raise WsSettingsError(f"port {port} is already in use")

    _apply(cfg)
    if bridge_port is not None:
        privileged.call("service_restart", {"name": "sshws-bridge"})
    db.log_action(actor, "ports_update", None,
                  f"ws={cfg['ws_port']} wss={cfg['wss_port']} bridge={cfg['bridge_port']}", success=True)
    return cfg
