import sys
from pathlib import Path

import pytest

MANAGER_DIR = Path(__file__).resolve().parents[2] / "manager"
if str(MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(MANAGER_DIR))


@pytest.fixture(autouse=True)
def isolated_sshws_paths(tmp_path, monkeypatch):
    """Point every SSHWS_* path at a throwaway directory for this test only."""
    monkeypatch.setenv("SSHWS_ETC", str(tmp_path / "etc"))
    monkeypatch.setenv("SSHWS_VAR", str(tmp_path / "var"))
    monkeypatch.setenv("SSHWS_LOG", str(tmp_path / "log"))
    monkeypatch.setenv("SSHWS_ROOT", str(tmp_path / "opt"))
    monkeypatch.setenv("SSHWS_BACKUP_DIR", str(tmp_path / "var" / "backups"))
    monkeypatch.setenv("SSHWS_NGINX_SITE", str(tmp_path / "nginx-site.conf"))
    monkeypatch.setenv("SSHWS_NGINX_LINK", str(tmp_path / "nginx-link.conf"))
    monkeypatch.setenv("SSHWS_PAM_LIMITS", str(tmp_path / "limits.conf"))
    monkeypatch.setenv("SSHWS_SUDOERS", str(tmp_path / "sudoers"))
    yield tmp_path
