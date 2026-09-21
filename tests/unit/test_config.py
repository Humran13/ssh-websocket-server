import pytest
from core import config as config_mod


def test_defaults_round_trip():
    cfg = config_mod.load()
    assert cfg["ssh_port"] == 22
    assert cfg["ws_paths"] == ["/ssh"]
    config_mod.save(cfg)
    reloaded = config_mod.load()
    assert reloaded == cfg


def test_save_rejects_missing_keys():
    with pytest.raises(config_mod.ConfigError):
        config_mod.validate({"ssh_port": 22})


def test_port_conflict_rejected():
    cfg = config_mod.load()
    cfg["ws_port"] = cfg["ssh_port"]
    with pytest.raises(config_mod.ConfigError, match="port conflict"):
        config_mod.validate(cfg)


@pytest.mark.parametrize("port", [0, -1, 65536, 999999])
def test_invalid_ports_rejected(port):
    cfg = config_mod.load()
    cfg["ws_port"] = port
    with pytest.raises(config_mod.ConfigError):
        config_mod.validate(cfg)


def test_privileged_port_rejected_for_non_ssh_fields():
    cfg = config_mod.load()
    cfg["manager_port"] = 500
    with pytest.raises(config_mod.ConfigError, match="privileged port"):
        config_mod.validate(cfg)


@pytest.mark.parametrize("path", ["/ssh", "/ws", "/a/b-c_d.e~f"])
def test_valid_ws_paths(path):
    assert config_mod.validate_ws_path(path) == path


@pytest.mark.parametrize("path", ["ssh", "/../etc/passwd", "/a//b", "", "/" + "a" * 200])
def test_invalid_ws_paths(path):
    with pytest.raises(config_mod.ConfigError):
        config_mod.validate_ws_path(path)


@pytest.mark.parametrize("domain", ["example.com", "vpn.example.co.uk", "a-b.example.com"])
def test_valid_domains(domain):
    assert config_mod.validate_domain(domain) == domain


@pytest.mark.parametrize(
    "domain", ["", "no-tld", "-bad.com", "bad-.com", "has space.com", "a" * 260 + ".com"]
)
def test_invalid_domains(domain):
    with pytest.raises(config_mod.ConfigError):
        config_mod.validate_domain(domain)


def test_domain_mode_requires_domain():
    cfg = config_mod.load()
    cfg["install_mode"] = "domain"
    cfg["domain"] = None
    with pytest.raises(config_mod.ConfigError, match="no domain"):
        config_mod.validate(cfg)


def test_no_config_file_returns_defaults(tmp_path):
    assert not (tmp_path / "etc" / "config.json").exists()
    cfg = config_mod.load()
    assert cfg["version"] == "0.1.0"
