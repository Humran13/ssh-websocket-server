"""Backup / restore of manager-owned state.

Included by default: config.json, the SQLite metadata DB (admin accounts +
managed-user bookkeeping + audit log), and the rendered Nginx site file.
SSL private keys are only included if the caller explicitly opts in --
they are copied out through the privileged helper (see
scripts/priv_helper.py: action_certs_export) so the unprivileged manager
process never needs read access to /etc/letsencrypt itself, and the
resulting archive is clearly named so nobody mistakes it for a
credential-free backup.
"""
from __future__ import annotations

import json
import secrets
import shutil
import tarfile
import tempfile
import time
from pathlib import Path

from . import paths, privileged

MANIFEST_NAME = "manifest.json"


class BackupError(RuntimeError):
    pass


def create_backup(include_ssl: bool = False, actor: str = "system") -> Path:
    paths.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    suffix = "-with-ssl-keys" if include_ssl else ""
    # A short random token (not just the timestamp) guarantees uniqueness even
    # when two backups are requested within the same second -- two backups
    # silently colliding and overwriting each other would be far worse than
    # an extra few characters in the filename.
    archive_name = f"backup-{ts}-{secrets.token_hex(3)}{suffix}.tar.gz"
    archive_path = paths.BACKUP_DIR / archive_name

    with tempfile.TemporaryDirectory(prefix="sshws-backup-") as tmp:
        stage = Path(tmp)
        manifest = {"created_at": ts, "include_ssl": include_ssl, "files": []}

        for src in (paths.CONFIG_FILE, paths.DB_FILE):
            if src.exists():
                dst = stage / src.name
                shutil.copy2(src, dst)
                manifest["files"].append(src.name)

        if paths.NGINX_SITE_FILE.exists():
            try:
                shutil.copy2(paths.NGINX_SITE_FILE, stage / "nginx-site.conf")
                manifest["files"].append("nginx-site.conf")
            except PermissionError:
                pass

        if include_ssl:
            from . import config as config_mod
            cfg = config_mod.load()
            domain = cfg.get("domain")
            if not domain:
                raise BackupError("SSL export requested but no domain is configured")
            data = privileged.call("certs_export", {"domain": domain})
            export_dir = Path(data["export_dir"])
            ssl_dir = stage / "ssl"
            ssl_dir.mkdir()
            for fname in data.get("files", []):
                shutil.move(str(export_dir / fname), str(ssl_dir / fname))
            shutil.rmtree(export_dir, ignore_errors=True)
            manifest["files"].append("ssl/")

        (stage / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        with tarfile.open(archive_path, "w:gz") as tar:
            for item in stage.iterdir():
                tar.add(item, arcname=item.name)

    archive_path.chmod(0o600)
    # Same reasoning as restore_backup()'s chown calls: create_backup()
    # can run as root (`ssh-ws` -> Backup, or update.sh's pre-update
    # backup) as well as unprivileged (the web panel). A root-made,
    # root-owned, mode-0600 archive would otherwise be invisible to the
    # web panel's own download/restore routes, which run unprivileged.
    paths.chown_to_service_user(archive_path)
    return archive_path


def list_backups() -> list[Path]:
    if not paths.BACKUP_DIR.exists():
        return []
    return sorted(paths.BACKUP_DIR.glob("backup-*.tar.gz"), reverse=True)


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        member_path = (dest / member.name).resolve()
        if not str(member_path).startswith(str(dest_resolved)):
            raise BackupError(f"refusing to extract member outside target directory: {member.name}")
    tar.extractall(dest, filter="data")  # noqa: S202 - paths already validated above


def restore_backup(archive_path: Path) -> dict:
    if not archive_path.exists():
        raise BackupError(f"backup file not found: {archive_path}")

    safety_backup = create_backup(include_ssl=False, actor="restore-safety")

    with tempfile.TemporaryDirectory(prefix="sshws-restore-") as tmp:
        stage = Path(tmp)
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extract(tar, stage)

        manifest_path = stage / MANIFEST_NAME
        if not manifest_path.exists():
            raise BackupError("archive is missing manifest.json -- not a valid backup")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        from . import config as config_mod
        restored_config = stage / paths.CONFIG_FILE.name
        if restored_config.exists():
            cfg = json.loads(restored_config.read_text(encoding="utf-8"))
            config_mod.validate(cfg)  # fail fast before touching anything

        if restored_config.exists():
            paths.ETC_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(restored_config, paths.CONFIG_FILE)
            # restore_backup() can run as root (the `ssh-ws` CLI, or
            # update.sh's rollback path) as well as unprivileged (the web
            # panel) -- shutil.copy2 never changes ownership, so a
            # root-run restore would otherwise leave a root-owned
            # config.json the always-unprivileged manager can't read.
            paths.chown_to_service_user(paths.CONFIG_FILE)

        restored_db = stage / paths.DB_FILE.name
        if restored_db.exists():
            paths.VAR_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(restored_db, paths.DB_FILE)
            paths.chown_to_service_user(paths.DB_FILE)

    return {"manifest": manifest, "safety_backup": str(safety_backup)}
