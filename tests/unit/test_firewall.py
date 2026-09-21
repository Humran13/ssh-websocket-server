import pytest

from core import config as config_mod, db, firewall


@pytest.fixture(autouse=True)
def _init_db():
    db.init_db()


def test_sync_rules_always_allows_current_ssh_port(monkeypatch):
    allowed_ports = []

    def fake_call(action, args=None, timeout=40):
        if action == "ufw_allow":
            allowed_ports.append(args["port"])
        return {}

    monkeypatch.setattr(firewall.privileged, "call", fake_call)
    cfg = config_mod.load()
    cfg["ssh_port"] = 2222
    config_mod.save(cfg)

    result = firewall.sync_rules(actor="admin")
    assert 2222 in allowed_ports
    assert 2222 in result["allowed_ports"]


def test_enable_syncs_before_enabling(monkeypatch):
    order = []

    def fake_call(action, args=None, timeout=40):
        order.append(action)
        return {}

    monkeypatch.setattr(firewall.privileged, "call", fake_call)
    firewall.enable(actor="admin")
    assert order.index("ufw_allow") < order.index("ufw_enable")


def test_status_unknown_when_helper_unavailable(monkeypatch):
    from core import privileged

    def failing_call(action, args=None, timeout=40):
        raise privileged.PrivilegedActionError("no sudo")

    monkeypatch.setattr(firewall.privileged, "call", failing_call)
    result = firewall.status()
    assert result["active"] is False
