from core import logs


def test_sanitize_redacts_password():
    line = "user auth: username=bob password=hunter2 success"
    out = logs.sanitize(line)
    assert "hunter2" not in out
    assert "[REDACTED]" in out


def test_sanitize_redacts_private_key_block():
    line = "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----"
    out = logs.sanitize(line)
    assert "MIIB" not in out
    assert "REDACTED PRIVATE KEY" in out


def test_sanitize_redacts_cookie():
    line = "GET /panel Cookie: session=abc123def456"
    out = logs.sanitize(line)
    assert "abc123def456" not in out


def test_sanitize_leaves_normal_lines_alone():
    line = "2026-01-01 sshd[123]: Accepted publickey for alice from 10.0.0.5"
    assert logs.sanitize(line) == line


def test_unknown_source_raises():
    import pytest
    with pytest.raises(ValueError):
        logs.tail("not-a-real-source")


def test_available_sources_includes_expected():
    sources = logs.available_sources()
    for expected in ("ssh", "bridge", "nginx", "manager", "certbot", "install"):
        assert expected in sources
