# Backup and restore

## What's included

Every backup (`ssh-ws` -> Backup, or the panel's Backup page) is a
`tar.gz` containing:

- `manifest.json` -- what's in the archive and when it was made
- `config.json` -- the full WebSocket/domain/port configuration
- `manager.db` -- the SQLite metadata database: admin accounts (hashed
  passwords only), which OS accounts this project manages and their
  expiry/session-limit settings, and the audit log
- `nginx-site.conf` -- the rendered Nginx site config

**SSH user accounts themselves (the real OS accounts in `/etc/passwd` /
`/etc/shadow`) are not part of the backup.** They are restored by
Ubuntu's own user-management tools, not by this project; what this
project backs up is the *metadata* about which accounts it created and
their settings, so that after a restore the panel/CLI correctly
recognizes them again.

## SSL private keys

Off by default. Checking "Include SSL private key" (panel) or answering
yes to the CLI's prompt copies the current domain's Let's Encrypt
`fullchain.pem`/`privkey.pem` into the archive via the privileged helper
(`scripts/priv_helper.py::action_certs_export`) -- the unprivileged
manager process itself never reads `/etc/letsencrypt` directly.

The resulting archive is:
- named with a `-with-ssl-keys` suffix so it's never mistaken for an
  ordinary backup,
- written with file mode `0600`,
- and should be handled with the same care as the private key itself --
  download it over a trusted connection, store it somewhere access
  controlled, and delete old copies you no longer need.

## Restore

`restore_backup()` (`manager/core/backup.py`) always:

1. Takes an automatic **safety backup** of the current state first.
2. Extracts to a temporary directory, validating every archive member's
   path stays inside that directory (rejecting `../` traversal) before
   touching the filesystem, on top of Python's own tarfile `"data"`
   extraction filter.
3. Validates `manifest.json` is present and `config.json` (if included)
   passes the same validation the live config always goes through --
   before anything is overwritten.
4. Only then copies files into place.

If anything after step 1 fails, the safety backup taken in step 1 is left
in place and the original files are untouched (the failure happens before
any copy-into-place step runs). After a restore, restart services
(`ssh-ws` -> Restart Services) to pick up the restored config.
