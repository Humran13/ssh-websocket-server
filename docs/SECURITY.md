# Security architecture and review

## Privilege model

The web panel (`sshws-manager.service`) and the WebSocket bridge
(`sshws-bridge.service`) both run continuously as the unprivileged system
account `sshws` -- neither ever runs as root.

Every operation that genuinely needs root (creating/locking/deleting an OS
user, changing a password, editing `/etc/security/limits.d/`, reloading
Nginx, running `ufw`/`certbot`, restarting a systemd unit) goes through
exactly one path: `manager/core/privileged.py` calling
`scripts/priv_helper.py` as root via a single, narrow sudoers rule:

```
sshws ALL=(root) NOPASSWD: <venv-python> <install-root>/scripts/priv_helper.py
```

There is no wildcard in that rule -- the helper takes no arguments at all.
Instead it reads one JSON object (`{"action": ..., "args": {...}}`) from
**stdin**, so a new password or any other secret never appears as a
command-line argument (and therefore never in `ps`, shell history, or
audit logs that capture argv). `priv_helper.py` implements an **allowlist**
of named actions (see the `ACTIONS` dict at the bottom of that file); there
is no "run an arbitrary command" action. Every argument the caller supplies
(username, domain, WebSocket path, port, service name, PID to kill) is
validated against a strict pattern before it touches a subprocess call,
and every subprocess call uses an argument array (`subprocess.run([...],
shell=False)`) -- nothing is ever interpolated into a shell string.

Destructive user actions additionally check that the target account is one
this project actually created (tracked in the `managed_users` SQLite
table) and has `uid >= 1000`; a hard-coded denylist also blocks `root`,
`sshws` itself, and every standard Ubuntu system account by name, even if
somehow passed in.

The `ssh-ws` CLI is different: it is meant to be run interactively by a
human administrator via `sudo`, so it runs as root directly and calls the
same allowlisted action functions in-process (skipping the sudo
round-trip) -- the validation is identical either way, only the transport
differs. See `manager/core/privileged.py::_call_in_process`.

## Web application

* **Authentication**: a single admin-account table, `werkzeug.security`
  PBKDF2 password hashing, no default/blank password -- the first run
  redirects to a one-time `/setup` page that requires a 12+ character
  password.
* **Sessions**: Flask's signed session cookie, `HttpOnly`, `SameSite=Lax`,
  `Secure` whenever the app believes it's behind TLS (default on; disable
  only for local HTTP-only testing via `SSHWS_FORCE_SECURE_COOKIE=0`), 8
  hour lifetime, secret key generated once at install time and stored at
  `/etc/ssh-websocket-server/secret_key` with mode `0600`.
* **CSRF**: every state-changing form is protected by Flask-WTF's
  `CSRFProtect`, enabled globally in `create_app()`.
* **Rate limiting**: `/login` is limited to 10 attempts / 5 minutes per
  source IP (Flask-Limiter), independent of which username is tried.
* **Command/shell injection**: the web app never calls `subprocess` or
  `os.system` directly -- all system interaction goes through
  `manager/core/*.py`, which in turn goes through the validated,
  argument-array-only privileged helper described above.
* **Path traversal**: backup download/restore resolve the requested
  filename with `werkzeug.utils.secure_filename` and verify the resolved
  path's parent is exactly the backup directory before touching it.
  Restore itself validates every tar member path stays inside the
  extraction directory before extracting (`core/backup.py::_safe_extract`)
  and Python's own tarfile "data" filter as a second layer.
* **Arbitrary file access**: log viewing only ever reads from a
  hard-coded allowlist of journald units / log file paths
  (`core/logs.py`), never a caller-supplied path.
* **Log redaction**: `core/logs.py` strips passwords, tokens, secrets,
  session IDs, cookies and PEM private-key blocks from every log line
  before it is displayed or returned.
* **Security headers**: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, a restrictive `Content-Security-Policy`, and
  `Referrer-Policy: same-origin` are set on every response.

## Firewall safety

`core/firewall.py::enable()` always calls `sync_rules()` (which allows the
*current* SSH port plus every active WS/WSS/manager port) immediately
before enabling UFW, in the same call -- there is no code path that can
enable the firewall without first allowing the SSH port the administrator
is connected on. `install.sh` performs the same allow-before-enable
sequence during setup.

## TLS / certificates

Certificates are obtained via the system `certbot` package (not a
third-party downloaded binary) using the standard `--nginx` plugin.
Private keys are never read by the unprivileged manager process directly;
when a backup with `--include-ssl` is requested, the privileged helper
copies the key material to a directory owned by `sshws` with mode `0600`,
the unprivileged backup code moves it into the archive and deletes the
export directory, and the resulting archive itself is written with mode
`0600` and named to include `-with-ssl-keys` so it's never mistaken for an
ordinary, safe-to-share backup.

## Findings from the pre-1.0 review

The following issues were found and fixed during development (kept here
for the record rather than silently fixed with no trace):

1. **Backup filename collision** -- `core/backup.py` originally named
   archives using only a whole-second timestamp. Two backups requested
   within the same second (which happens routinely: `restore_backup()`
   takes an automatic "safety backup" immediately before restoring)
   collided and silently overwrote each other, which could destroy the
   very backup being restored from. Fixed by adding a random suffix to
   every backup filename, verified with a dedicated regression test
   (`tests/unit/test_backup.py::test_restore_backup_round_trip`).

No other exploitable issues (privilege escalation path, injection, XSS,
credential exposure) were identified as of this writing. This is a
young project; treat this section as a living document, not a guarantee.
