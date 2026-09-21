import pytest

from core import config as config_mod, db, domain, paths


@pytest.fixture(autouse=True)
def _init_db():
    db.init_db()


@pytest.fixture(autouse=True)
def _fake_privileged(monkeypatch):
    def fake_call(action, args=None, timeout=40):
        if action == "nginx_test":
            return {"ok": True, "output": "syntax ok"}
        return {"ok": True}

    monkeypatch.setattr(domain.privileged, "call", fake_call)


def test_issue_certificate_uses_extended_timeout(monkeypatch):
    # priv_helper.py itself gives certbot up to 180s internally (network
    # round trips to Let's Encrypt); the default 40s here would otherwise
    # kill the sudo-wrapped process -- and therefore certbot -- well
    # before that inner timeout could ever matter.
    calls = []

    def fake_call(action, args=None, timeout=40):
        calls.append((action, timeout))
        if action == "nginx_test":
            return {"ok": True, "output": "ok"}
        return {"ok": True}

    monkeypatch.setattr(domain.privileged, "call", fake_call)
    domain.set_domain("vpn.example.com", actor="admin")
    domain.issue_certificate(None, actor="admin")

    issue_calls = [t for a, t in calls if a == "certbot_issue"]
    assert issue_calls == [200]


def test_dns_check_invalid_domain_raises():
    with pytest.raises(config_mod.ConfigError):
        domain.dns_check("not a domain")


def test_dns_check_nonexistent_domain():
    result = domain.dns_check("this-domain-should-not-exist-in-dns.invalid")
    assert result["resolves"] is False
    assert result["matches_server"] is False


def test_set_domain_updates_config():
    domain.set_domain("vpn.example.com", actor="admin")
    cfg = config_mod.load()
    assert cfg["domain"] == "vpn.example.com"
    assert cfg["install_mode"] == "domain"


def test_remove_domain_disables_wss():
    domain.set_domain("vpn.example.com", actor="admin")
    cfg = config_mod.load()
    cfg["wss_enabled"] = True
    cfg["ssl_cert_path"] = "/etc/letsencrypt/live/vpn.example.com/fullchain.pem"
    cfg["ssl_key_path"] = "/etc/letsencrypt/live/vpn.example.com/privkey.pem"
    config_mod.save(cfg)

    domain.remove_domain(actor="admin")
    cfg = config_mod.load()
    assert cfg["domain"] is None
    assert cfg["install_mode"] == "ip"
    assert cfg["wss_enabled"] is False


def test_nginx_apply_rolls_back_on_invalid_config(monkeypatch):
    domain.set_domain("vpn.example.com", actor="admin")

    def failing_nginx_test(action, args=None, timeout=40):
        if action == "nginx_test":
            return {"ok": False, "output": "syntax error"}
        return {"ok": True}

    monkeypatch.setattr(domain.privileged, "call", failing_nginx_test)
    with pytest.raises(domain.DomainError, match="invalid"):
        domain.set_domain("broken.example.com", actor="admin")


def test_apply_nginx_never_writes_site_file_directly(monkeypatch):
    # /etc/nginx/sites-available/ is root-owned in production; the
    # unprivileged manager process must never write there itself -- only
    # the (mocked-here) privileged helper "writes" the live site file. If
    # this regresses to a direct filesystem write, this file would exist
    # on disk even though only the fake privileged.call ran.
    calls = []

    def fake_call(action, args=None, timeout=40):
        calls.append(action)
        if action == "nginx_test":
            return {"ok": True, "output": "ok"}
        return {"ok": True}

    monkeypatch.setattr(domain.privileged, "call", fake_call)
    domain.set_domain("vpn.example.com", actor="admin")

    assert "nginx_write_site" in calls
    assert not paths.NGINX_SITE_FILE.exists()


def test_apply_nginx_sends_rendered_content_to_privileged_write(monkeypatch):
    captured = {}

    def fake_call(action, args=None, timeout=40):
        if action == "nginx_write_site":
            captured["content"] = args["content"]
        if action == "nginx_test":
            return {"ok": True, "output": "ok"}
        return {"ok": True}

    monkeypatch.setattr(domain.privileged, "call", fake_call)
    domain.set_domain("vpn.example.com", actor="admin")

    assert "server_name vpn.example.com;" in captured["content"]


def test_rollback_restores_previous_site_via_privileged_write(monkeypatch):
    # Simulate a site file that a prior (real) privileged write already put
    # in place, world-readable as priv_helper.py's writer leaves it.
    paths.NGINX_SITE_FILE.parent.mkdir(parents=True, exist_ok=True)
    original_content = "server { listen 80; server_name original.example.com; }\n"
    paths.NGINX_SITE_FILE.write_text(original_content, encoding="utf-8")

    written = []

    def failing_call(action, args=None, timeout=40):
        if action == "nginx_write_site":
            written.append(args["content"])
            return {"path": str(paths.NGINX_SITE_FILE)}
        if action == "nginx_test":
            return {"ok": False, "output": "syntax error"}
        return {"ok": True}

    monkeypatch.setattr(domain.privileged, "call", failing_call)
    with pytest.raises(domain.DomainError):
        domain.set_domain("broken.example.com", actor="admin")

    # First write is the (invalid) new config; the rollback write restores
    # the original content read from this project's own backup directory.
    assert len(written) == 2
    assert written[-1] == original_content

    backups = list((paths.VAR_DIR / "nginx-backups").glob("*.conf.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original_content
