import socket

from core import config as config_mod
from core import network


def test_render_nginx_config_ip_mode():
    cfg = config_mod.load()
    rendered = network.render_nginx_config(cfg)
    assert "listen 80" in rendered
    assert "location /ssh" in rendered
    assert "proxy_pass http://127.0.0.1:8765" in rendered
    assert "server_name _;" in rendered
    assert "wss" not in rendered.lower() or "listen 443 ssl" not in rendered


def test_render_nginx_config_domain_and_wss():
    cfg = config_mod.load()
    cfg["install_mode"] = "domain"
    cfg["domain"] = "vpn.example.com"
    cfg["wss_enabled"] = True
    cfg["ssl_cert_path"] = "/etc/letsencrypt/live/vpn.example.com/fullchain.pem"
    cfg["ssl_key_path"] = "/etc/letsencrypt/live/vpn.example.com/privkey.pem"
    rendered = network.render_nginx_config(cfg)
    assert "server_name vpn.example.com;" in rendered
    assert "listen 443 ssl" in rendered
    assert "ssl_certificate /etc/letsencrypt/live/vpn.example.com/fullchain.pem;" in rendered


def test_render_nginx_multiple_ws_paths():
    cfg = config_mod.load()
    cfg["ws_paths"] = ["/ssh", "/ws", "/websocket"]
    rendered = network.render_nginx_config(cfg)
    for p in cfg["ws_paths"]:
        assert f"location {p}" in rendered


def test_is_port_free_detects_bound_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        assert network.is_port_free(port, host="127.0.0.1") is False
    finally:
        s.close()


def test_is_port_free_true_for_unused_high_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert network.is_port_free(port, host="127.0.0.1") is True


def test_write_nginx_config(tmp_path):
    cfg = config_mod.load()
    site_file = tmp_path / "site.conf"
    network.write_nginx_config(cfg, site_file)
    assert site_file.exists()
    assert "listen 80" in site_file.read_text()
