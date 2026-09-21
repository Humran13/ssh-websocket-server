import tarfile
import time
from pathlib import Path

import pytest

from core import backup, config as config_mod, db


@pytest.fixture(autouse=True)
def _init_db():
    db.init_db()


def test_create_backup_contains_manifest_config_and_db():
    cfg = config_mod.load()
    cfg["domain"] = None
    config_mod.save(cfg)

    archive = backup.create_backup(include_ssl=False, actor="tester")
    assert archive.exists()
    assert archive.name.startswith("backup-")
    assert "with-ssl-keys" not in archive.name

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "manifest.json" in names
    assert "config.json" in names
    assert "manager.db" in names


def test_list_backups_sorted_newest_first():
    a = backup.create_backup(actor="t")
    time.sleep(1.1)
    b = backup.create_backup(actor="t")
    listed = backup.list_backups()
    assert listed[0] == b
    assert listed[1] == a


def test_restore_backup_round_trip():
    cfg = config_mod.load()
    cfg["ws_port"] = 8080
    config_mod.save(cfg)
    archive = backup.create_backup(actor="tester")

    cfg2 = config_mod.load()
    cfg2["ws_port"] = 9999
    config_mod.save(cfg2)
    assert config_mod.load()["ws_port"] == 9999

    result = backup.restore_backup(archive)
    assert config_mod.load()["ws_port"] == 8080
    assert Path(result["safety_backup"]).exists()


def test_restore_rejects_missing_file(tmp_path):
    with pytest.raises(backup.BackupError, match="not found"):
        backup.restore_backup(tmp_path / "nope.tar.gz")


def test_restore_rejects_archive_without_manifest(tmp_path):
    bad_archive = tmp_path / "bad.tar.gz"
    junk = tmp_path / "junk.txt"
    junk.write_text("hi")
    with tarfile.open(bad_archive, "w:gz") as tar:
        tar.add(junk, arcname="junk.txt")
    with pytest.raises(backup.BackupError, match="manifest"):
        backup.restore_backup(bad_archive)


def test_restore_rejects_path_traversal(tmp_path):
    evil_archive = tmp_path / "evil.tar.gz"
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"created_at": "x", "include_ssl": false, "files": []}')
    with tarfile.open(evil_archive, "w:gz") as tar:
        tar.add(manifest, arcname="manifest.json")
        info = tarfile.TarInfo(name="../../evil.txt")
        info.size = 4
        import io
        tar.addfile(info, io.BytesIO(b"evil"))
    with pytest.raises(backup.BackupError, match="outside target directory"):
        backup.restore_backup(evil_archive)


def test_backup_archive_permissions_restricted():
    archive = backup.create_backup(actor="tester")
    import stat
    mode = stat.S_IMODE(archive.stat().st_mode)
    # Windows doesn't enforce POSIX perms the same way; only assert on POSIX.
    if hasattr(os := __import__("os"), "chmod") and os.name != "nt":
        assert mode == 0o600
