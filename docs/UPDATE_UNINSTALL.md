# Update and uninstall

## Update (`update.sh` / `ssh-ws` -> Update)

1. Takes a full backup (`core.backup.create_backup`) before touching
   anything.
2. If `/opt/ssh-websocket-server` is a git checkout, fetches and checks
   out the target ref (default: `main`); otherwise skips the code-fetch
   step and only refreshes dependencies/services (covers a from-source /
   non-git install).
3. Reinstalls Python dependencies from the (possibly updated)
   `manager/requirements.txt`.
4. Re-renders the systemd units from the current template with the
   same environment-specific values already on disk (picks up hardening
   or config changes shipped in the update without needing to re-ask the
   administrator anything).
5. Runs `core.db.init_db()` (idempotent `CREATE TABLE IF NOT EXISTS`) as
   the migration hook for future schema changes.
6. Restarts `sshws-bridge` / `sshws-manager`, reloads Nginx.
7. Runs the full health-check suite (`core.health.run_all()`).
8. **If any health check fails**, automatically rolls back: checks the
   git tree back out to the pre-update commit, restores the pre-update
   backup, reinstalls the old dependency set, restarts services, and
   exits non-zero with the backup path in the output.

## Uninstall (`uninstall.sh` / `ssh-ws` -> Uninstall)

Prints an itemized list of exactly what will and will not be removed
before doing anything, and (outside of `--yes`) requires confirmation.

Removed: the two systemd services, this project's Nginx site (only --
other sites are left alone), the Fail2ban jail file this project added,
the sudoers rule, the `ssh-ws` command, `/opt/ssh-websocket-server`,
`/etc/ssh-websocket-server`, `/var/lib/ssh-websocket-server`, and the
`sshws` service account. `/var/log/ssh-websocket-server` is renamed
(kept) rather than deleted, so install/operation history survives an
uninstall by default.

**Never removed** unless you pass `--remove-managed-users` explicitly:
the SSH accounts this project created. OpenSSH itself, your own SSH
access, and every unrelated Nginx site/Fail2ban jail are never touched
at all, with or without that flag.

If Nginx's stock default site was disabled during install (see
`install.sh`'s "Preparing Nginx" step), its config file was backed up
rather than deleted; uninstall does not automatically restore it, but
tells you where the backup is so you can re-enable it in one command if
you want the stock welcome page back.
