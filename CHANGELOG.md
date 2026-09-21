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
- 94 automated unit tests (pytest) covering config/port/domain/path
  validation, user lifecycle and safety rules, auth/password handling,
  Nginx rendering, backup/restore (including a path-traversal regression
  test), domain/WSS state transitions, firewall allow-before-enable
  ordering, and log redaction. `shellcheck` and `ruff` both clean.
- Docker-based integration test harness
  (`tests/integration/run-matrix.sh`) that runs the real installer inside
  a systemd-capable container per supported Ubuntu version and verifies
  sshd/Nginx/WebSocket-handshake/manager all come up; results in
  `docs/COMPATIBILITY.md`.

### Known limitations
- Not yet tested against a real cloud VPS (see README "Known limitations").
- Per-user bandwidth accounting intentionally not implemented (would
  require a fragile/misleading approach); documented as a future feature.
- Ubuntu 18.04 package availability is constrained by its EOL status.
