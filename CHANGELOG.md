# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versioning is
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-09-21

Initial release.

### Added
- One-command installer (`install.sh`) for Ubuntu 18.04/20.04/22.04/24.04/26.04
  (amd64 primary, arm64 best-effort): OS/arch detection, port checks,
  dependency install, systemd services, Nginx WS/WSS reverse proxy,
  firewall (UFW) and Fail2ban configuration, CLI installation, health
  checks, and a connection-info summary.
- Three SSH connection modes backed by one OpenSSH instance: direct SSH,
  plain WebSocket (`ws://`), secure WebSocket (`wss://`), each with
  configurable ports and WebSocket path(s).
- Domain + automatic Let's Encrypt certificate support, with DNS sanity
  checking, backup-before-apply and rollback-on-failure for every Nginx
  change.
- Flask + SQLite web management panel ("SSH WebSocket Manager"):
  dashboard, SSH user lifecycle (create/enable/disable/delete/password/
  expiry/session-limit), active-session view with disconnect, WebSocket
  settings, domain/SSL management, firewall status, log viewer (with
  secret redaction), backup/restore.
- `ssh-ws` interactive CLI, sharing 100% of its business logic with the
  web panel via `manager/core/*.py`.
- Per-user concurrent SSH session limits enforced via the standard
  `pam_limits` `maxlogins` mechanism.
- Security architecture: unprivileged service account for all long-running
  processes; a single, narrowly-scoped root helper
  (`scripts/priv_helper.py`) reached through one wildcard-free sudoers
  rule, with an allowlist of validated actions and stdin-only secret
  transport; CSRF protection, rate-limited login, hardened session
  cookies, and security headers on the web panel. Full write-up in
  `docs/SECURITY.md`.
- `update.sh` / `ssh-ws update`: pre-update backup, code/dependency
  refresh, systemd unit refresh, DB migration hook, health-check-gated
  rollback on failure.
- `uninstall.sh` / `ssh-ws uninstall`: explicit, itemized removal that
  never touches unrelated Nginx sites or unmanaged SSH accounts.
- 104 automated unit tests (pytest) covering config/port/domain/path
  validation, user lifecycle and safety rules, auth/password handling,
  Nginx rendering, backup/restore (including a path-traversal regression
  test), domain/WSS state transitions, firewall allow-before-enable
  ordering, log redaction, and the session-secret-key generation race
  (verified with a real multi-threaded test). `shellcheck` and `ruff`
  both clean.
- Docker-based integration test harness
  (`tests/integration/run-matrix.sh`) that runs the real installer inside
  a systemd-capable container per supported Ubuntu version and verifies
  sshd/Nginx/WebSocket-handshake/manager all come up; results in
  `docs/COMPATIBILITY.md`.

### Fixed during pre-release testing
Found and fixed via the Docker-based integration matrix and a subsequent
security-focused code review -- kept here rather than silently folded in,
per this project's own "document limitations/findings" standard:
- `/etc/ssh-websocket-server` etc. were root:sshws group-readable (0750),
  not writable by the service account that needs to create its own
  secret key/config/db there -- the manager crashed on first boot.
- Nginx site writes only worked at install time (root context); any
  post-install WS/domain change from the always-unprivileged manager
  would have hit the same permission wall. Now goes through a dedicated
  privileged-helper action.
- Stock-vs-customized Nginx default-site detection matched page content
  in `/var/www/html` instead of the config file itself, so it never
  actually detected the stock site and left it enabled, breaking IP-mode
  installs.
- The panel's CSP (`script-src 'self'`) silently blocked the inline
  `onsubmit="confirm(...)"` handlers used for delete/restore/disconnect
  confirmations -- those actions fired immediately with no prompt.
  Replaced with an external script.
- gunicorn's multiple worker processes could race generating the Flask
  session secret key on first boot, leaving two workers with two
  different keys and silently invalidating each other's sessions. Fixed
  with an atomic create-once helper, pre-created by the installer before
  any worker starts.
- `certbot`'s subprocess timeout (30s) was too tight for real Let's
  Encrypt network round trips.
- Ubuntu 18.04's default `python3` (3.6) cannot even parse this
  project's own code (`from __future__ import annotations` requires
  3.7+), let alone run the pinned Flask version (requires 3.8+).
  `install.sh` now installs `python3.8` from Ubuntu's own official
  archive for the venv specifically when the system Python is too old --
  verified end-to-end, not assumed.
- A backup-filename collision (same-second timestamps, no other entropy)
  could let a restore's own automatic safety-backup step silently
  overwrite the archive being restored from.

### Known limitations
- Not yet tested against a real cloud VPS (see README "Known limitations").
- Per-user bandwidth accounting intentionally not implemented (would
  require a fragile/misleading approach); documented as a future feature.
- UFW's `enable` step cannot be verified inside the Docker-based test
  sandbox (a missing `ip6_tables` kernel module in that specific
  container runtime, not an installer defect -- see
  `docs/COMPATIBILITY.md`); needs real-VPS verification.
- Ubuntu 18.04's apt archives are past standard EOL and frozen at that
  state; `certbot`/`python3-certbot-nginx` in particular may still be
  outdated or unavailable there without Ubuntu Pro ESM, independent of
  the Python-version fix above.
