"""Port/network helpers and Nginx config rendering.

Rendering is pure string templating (no shell, no eval) so it can be unit
tested without touching the filesystem or a real Nginx install.
"""
from __future__ import annotations

import socket
from pathlib import Path

from . import config as config_mod

NGINX_TEMPLATE_HTTP = """\
# Managed by ssh-websocket-server. Do not edit by hand -- changes will be
# overwritten by the panel/CLI. Back up first if you need to customize.
server {{
    listen {ws_port} {default_server};
    server_name {server_name};

{ws_locations}
    location {manager_path}/ {{
        proxy_pass http://127.0.0.1:{manager_port}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""

NGINX_TEMPLATE_HTTPS = """\
server {{
    listen {wss_port} ssl {default_server};
    server_name {server_name};

    ssl_certificate {ssl_cert_path};
    ssl_certificate_key {ssl_key_path};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

{ws_locations}
    location {manager_path}/ {{
        proxy_pass http://127.0.0.1:{manager_port}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""

WS_LOCATION_BLOCK = """\
    location {path} {{
        proxy_pass http://127.0.0.1:{bridge_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }}
"""


def render_nginx_config(cfg: dict) -> str:
    server_name = cfg["domain"] if cfg["install_mode"] == "domain" and cfg["domain"] else "_"
    default_server = "default_server" if server_name == "_" else ""
    ws_locations = "".join(
        WS_LOCATION_BLOCK.format(path=config_mod.validate_ws_path(p), bridge_port=cfg["bridge_port"])
        for p in cfg["ws_paths"]
    )

    parts = []
    if cfg["ws_enabled"]:
        parts.append(NGINX_TEMPLATE_HTTP.format(
            ws_port=cfg["ws_port"],
            default_server=default_server,
            server_name=server_name,
            ws_locations=ws_locations,
            manager_path=cfg["manager_path"].rstrip("/"),
            manager_port=cfg["manager_port"],
        ))
    if cfg["wss_enabled"] and cfg["ssl_cert_path"] and cfg["ssl_key_path"]:
        parts.append(NGINX_TEMPLATE_HTTPS.format(
            wss_port=cfg["wss_port"],
            default_server=default_server,
            server_name=server_name,
            ssl_cert_path=cfg["ssl_cert_path"],
            ssl_key_path=cfg["ssl_key_path"],
            ws_locations=ws_locations,
            manager_path=cfg["manager_path"].rstrip("/"),
            manager_port=cfg["manager_port"],
        ))
    return "\n".join(parts)


def is_port_free(port: int, host: str = "0.0.0.0") -> bool:  # noqa: S104 - default means "any interface"
    bind_host = None if host == "0.0.0.0" else host  # noqa: S104
    for family, socktype, _proto, _canon, sockaddr in socket.getaddrinfo(
            bind_host, port, type=socket.SOCK_STREAM):
        s = socket.socket(family, socktype)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(sockaddr)
        except OSError:
            return False
        finally:
            s.close()
    return True


def check_ports(ports: list[int]) -> dict[int, bool]:
    return {p: is_port_free(p) for p in ports}


def write_nginx_config(cfg: dict, site_file: Path) -> Path:
    site_file.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_nginx_config(cfg)
    site_file.write_text(rendered, encoding="utf-8")
    return site_file
