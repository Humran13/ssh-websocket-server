"""Domain / SSL lifecycle: switching between IP mode and domain+WSS mode.

Nginx config is always backed up before being overwritten, and a failed
certificate request never leaves the site config in a broken state --
Nginx config generation only ever references files/paths, and the new
config is validated with `nginx -t` (via the privileged helper) before
it is reloaded into the live config. On failure we keep the previous
site file in place (from the .bak copy) and reload with that instead.
"""
from __future__ import annotations

import socket
import time
from pathlib import Path

from . import config as config_mod
from . import network, paths, privileged, system_info


class DomainError(RuntimeError):
    pass


def dns_check(domain: str) -> dict:
    """Resolves the domain and reports whether it matches this host's
    best-guess public IP. Informational only -- never blocks a cert
    request, since split-horizon DNS / CDNs / multi-IP setups are common
    and a false negative here must not stop a legitimate certificate.
    """
    config_mod.validate_domain(domain)
    try:
        resolved = sorted({info[4][0] for info in socket.getaddrinfo(domain, None)})
    except socket.gaierror as exc:
        return {"resolves": False, "addresses": [], "matches_server": False, "error": str(exc)}
    server_ip = system_info.public_ip()
    return {
        "resolves": True,
        "addresses": resolved,
        "matches_server": bool(server_ip) and server_ip in resolved,
        "server_ip": server_ip,
    }


def _nginx_backup_dir() -> Path:
    d = paths.VAR_DIR / "nginx-backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _backup_nginx_site() -> Path | None:
    # /etc/nginx/sites-available/ is root-owned; the site file itself is
    # world-readable (0644, set by priv_helper.py's writer) so this read
    # needs no privilege, but the backup copy is kept under this project's
    # own (sshws-owned) directory rather than back into sites-available,
    # since writing there would hit the exact same permission wall the
    # live config write works around via the privileged helper.
    if not paths.NGINX_SITE_FILE.exists():
        return None
    backup = _nginx_backup_dir() / f"site-{int(time.time())}.conf.bak"
    backup.write_text(paths.NGINX_SITE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def _apply_nginx(cfg: dict) -> None:
    backup = _backup_nginx_site()
    rendered = network.render_nginx_config(cfg)
    try:
        privileged.call("nginx_write_site", {"content": rendered})
        result = privileged.call("nginx_test", {})
        if not result.get("ok"):
            raise DomainError(f"generated Nginx config is invalid: {result.get('output')}")
        privileged.call("service_reload", {"name": "nginx"})
    except Exception:
        if backup is not None:
            privileged.call("nginx_write_site", {"content": backup.read_text(encoding="utf-8")})
            privileged.call("service_reload", {"name": "nginx"})
        raise


def set_domain(domain: str, actor: str) -> dict:
    config_mod.validate_domain(domain)
    cfg = config_mod.load()
    cfg["domain"] = domain
    cfg["install_mode"] = "domain"
    config_mod.save(cfg)
    _apply_nginx(cfg)
    from . import db
    db.log_action(actor, "domain_set", domain, None, success=True)
    return dns_check(domain)


def remove_domain(actor: str) -> None:
    """Switch back to IP/WS mode. WSS is disabled (no cert is valid for
    an IP address) but the domain-specific certificate itself is left
    alone -- we never delete certificate material as a side effect of a
    config change."""
    cfg = config_mod.load()
    cfg["domain"] = None
    cfg["install_mode"] = "ip"
    cfg["wss_enabled"] = False
    config_mod.save(cfg)
    _apply_nginx(cfg)
    from . import db
    db.log_action(actor, "domain_removed", None, None, success=True)


def issue_certificate(email: str | None, actor: str) -> dict:
    cfg = config_mod.load()
    if not cfg["domain"]:
        raise DomainError("configure a domain before requesting a certificate")
    # Matches priv_helper.py's own 180s internal certbot timeout -- the
    # default 40s here would otherwise kill the sudo-wrapped process (and
    # therefore certbot) well before that inner timeout ever applies.
    result = privileged.call("certbot_issue", {"domain": cfg["domain"], "email": email}, timeout=200)
    from . import db
    db.log_action(actor, "certbot_issue", cfg["domain"], result.get("output"),
                  success=result.get("ok", False))
    if not result.get("ok"):
        raise DomainError(f"certificate request failed: {result.get('output')}")

    cfg["ssl_cert_path"] = f"/etc/letsencrypt/live/{cfg['domain']}/fullchain.pem"
    cfg["ssl_key_path"] = f"/etc/letsencrypt/live/{cfg['domain']}/privkey.pem"
    cfg["ssl_provider"] = "letsencrypt"
    cfg["wss_enabled"] = True
    config_mod.save(cfg)
    _apply_nginx(cfg)
    return result


def certificate_status() -> dict | None:
    cfg = config_mod.load()
    if not cfg["ssl_cert_path"]:
        return None
    expiry = system_info.ssl_expiry(cfg["ssl_cert_path"])
    return {"cert_path": cfg["ssl_cert_path"], "provider": cfg["ssl_provider"], "expires": expiry}
