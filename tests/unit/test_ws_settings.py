import pytest

from core import config as config_mod, db, ws_settings


@pytest.fixture(autouse=True)
def _init_db():
    db.init_db()


@pytest.fixture(autouse=True)
def _fake_privileged(monkeypatch):
    def fake_call(action, args=None, timeout=40):
        if action == "nginx_test":
            return {"ok": True, "output": "ok"}
        return {"ok": True}
    monkeypatch.setattr(ws_settings.privileged, "call", fake_call)
    monkeypatch.setattr(ws_settings.domain.privileged, "call", fake_call)


def test_update_paths_dedupes_and_validates():
    ws_settings.update_paths(["/ssh", "/ws", "/ssh"], actor="admin")
    assert config_mod.load()["ws_paths"] == ["/ssh", "/ws"]


def test_update_paths_rejects_empty():
    with pytest.raises(ws_settings.WsSettingsError):
        ws_settings.update_paths([], actor="admin")


def test_cannot_disable_both_ws_and_wss():
    with pytest.raises(ws_settings.WsSettingsError, match="at least one"):
        ws_settings.set_enabled(ws_enabled=False, wss_enabled=False, actor="admin")


def test_cannot_enable_wss_without_cert():
    with pytest.raises(ws_settings.WsSettingsError, match="certificate"):
        ws_settings.set_enabled(ws_enabled=True, wss_enabled=True, actor="admin")


def test_enable_wss_with_cert_present():
    cfg = config_mod.load()
    cfg["ssl_cert_path"] = "/etc/letsencrypt/live/x/fullchain.pem"
    cfg["ssl_key_path"] = "/etc/letsencrypt/live/x/privkey.pem"
    config_mod.save(cfg)
    ws_settings.set_enabled(ws_enabled=True, wss_enabled=True, actor="admin")
    assert config_mod.load()["wss_enabled"] is True


def test_update_ports_rejects_conflict():
    with pytest.raises(ws_settings.WsSettingsError):
        ws_settings.update_ports(ws_port=22, wss_port=None, bridge_port=None, actor="admin")
