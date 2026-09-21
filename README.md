# ssh-websocket-server

Install SSH-over-WebSocket access and a lightweight management panel on an
Ubuntu VPS with a single command.

> **Status**: v0.1.0, pre-release. The installer has been verified end-to-end
> inside systemd-capable Docker containers for the whole Ubuntu support
> matrix (see [Testing matrix](#testing-matrix)); it has **not** yet been
> run against a real cloud VPS. Read [Known limitations](#known-limitations)
> before using this in production.

## Features

- **Three ways in**: direct SSH, plain WebSocket (`ws://`), and secure
  WebSocket (`wss://`) -- all backed by the exact same OpenSSH server and
  the exact same user accounts.
- **Works with just an IP** (no domain required) or with a **domain +
  automatic Let's Encrypt certificate** for `wss://`.
- **Web management panel** ("SSH WebSocket Manager"): dashboard, SSH user
  lifecycle (create/disable/enable/delete/expiry/password), active-session
  view with disconnect, WebSocket/domain/SSL/firewall settings, log
  viewer, backup/restore.
- **`ssh-ws` CLI**: the same 20-option interactive menu you'd expect from
  a VPS panel, backed by the *exact same* business logic as the web
  panel -- not a separate reimplementation.
- **Security-first design**: the always-on web/bridge processes never run
  as root; a single narrowly-scoped root helper handles the few
  privileged operations that are actually needed, with every input
  validated and no argv-visible secrets. See
  [docs/SECURITY.md](docs/SECURITY.md).
- **Per-user concurrent session limits** via the standard Linux
  `pam_limits` `maxlogins` mechanism -- a real enforcement path, not a
  cosmetic counter.
- **Safe by default**: install/uninstall never touch unrelated Nginx
  sites or pre-existing SSH accounts; the firewall is always configured
  to allow your current SSH port *before* it's ever enabled; every config
  change is backed up before being overwritten, with automatic rollback
  on failure.

## One-line install

```bash
bash <(curl -Ls https://raw.githubusercontent.com/Humran13/ssh-websocket-server/main/install.sh)
```

Run it as root (or with `sudo`). It's interactive where it needs to be
(domain, ports, initial admin password) and safe to re-run.

Update an existing install:

```bash
sudo /opt/ssh-websocket-server/update.sh
# or: ssh-ws -> Update
```

Uninstall:

```bash
sudo /opt/ssh-websocket-server/uninstall.sh
```

Manage everything after install:

```bash
ssh-ws
```

## Architecture

```
Client
  │
  ├─ direct SSH ───────────────────────────────────────► OpenSSH (sshd)
  │
  └─ ws:// or wss:// ──► Nginx (TLS + WebSocket upgrade) ──► websockify
                          (reverse proxy)                    (WS↔TCP bridge)
                                                                    │
                                                                    ▼
                                                              OpenSSH (sshd)
```

- **OpenSSH** -- untouched, does what it always does. This project never
  replaces or weakens it.
- **websockify** -- the WebSocket↔TCP bridge. Chosen deliberately over a
  hand-rolled proxy: it's the small, actively-maintained library behind
  noVNC and is exactly the "bridge a WebSocket to a plain TCP service"
  tool this use case needs. Runs as the unprivileged `sshws` account,
  bound to localhost, forwarding to local sshd only.
- **Nginx** -- terminates TLS and reverse-proxies WebSocket upgrade
  requests to the bridge; also proxies the management panel.
- **Flask + SQLite** -- the web panel and its metadata (admin accounts,
  which OS accounts this project manages, audit log). SSH authentication
  itself always lives in the real `/etc/passwd`/`/etc/shadow`, never in
  this database.
- **systemd** -- `sshws-bridge.service` and `sshws-manager.service`, both
  running as the unprivileged `sshws` user with systemd hardening
  directives (`ProtectSystem=strict`, `NoNewPrivileges=true`, etc).
- **A single privileged helper** (`scripts/priv_helper.py`) -- the only
  thing that ever runs as root, invoked through one narrow, wildcard-free
  sudoers rule. See [docs/SECURITY.md](docs/SECURITY.md) for the full
  design.

## Supported Ubuntu versions

18.04, 20.04, 22.04, 24.04, 26.04 LTS, on **amd64** (primary) and **arm64**
(best-effort). See [Testing matrix](#testing-matrix) and
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for exactly what was
verified and known limitations (in particular: 18.04 is past standard EOL
and some packages there may be outdated/unavailable without Ubuntu Pro).

## WebSocket connection modes

| Mode | Example | Typical port |
|---|---|---|
| Direct SSH | `server.example.com:22` | 22 |
| Plain WebSocket | `ws://server.example.com/ssh` | 80 |
| Secure WebSocket | `wss://server.example.com/ssh` | 443 |
| IP + WebSocket (no domain) | `ws://203.0.113.10/ssh` | 80 |
| Custom ports | any of the above on 8080/8443/etc | configurable |

The WebSocket path (default `/ssh`) and every port are configurable from
the panel or `ssh-ws`, with conflict validation before anything is
applied. **Important**: `ws://`/`wss://` URLs are this server's endpoint,
not a string a plain `ssh` client accepts directly -- see
[docs/CLIENTS.md](docs/CLIENTS.md) for what actually connects to them and
how.

## Domain / WSS setup

From the panel (Domain/SSL) or `ssh-ws` -> "Domain / SSL":

1. Point your domain's A/AAAA record at the server's IP.
2. Set the domain. A DNS sanity check runs automatically (informational
   only -- it will not block you).
3. Request a Let's Encrypt certificate. WSS is enabled automatically once
   issuance succeeds.
4. Removing the domain switches back to IP/WS mode without deleting the
   certificate itself.

Every Nginx change is backed up first and validated with `nginx -t`
before being applied; a bad config is rolled back automatically.

## Web manager

Reachable at `http://<server-ip>:8088/` by default, and via Nginx at
`https://<domain>/panel` once a domain+certificate are configured. First
visit creates the initial admin account (12+ character password
required, PBKDF2-hashed, no default credentials). CSRF protection,
rate-limited login, and hardened session cookies are on by default -- see
[docs/SECURITY.md](docs/SECURITY.md).

## CLI manager

```
SSH WebSocket Server Manager

 1. Dashboard / Server Status        11. WebSocket Settings
 2. Add SSH User                     12. Domain / SSL
 3. List SSH Users                   13. Port Settings
 4. Change User Password             14. Firewall Status
 5. Extend User Expiry               15. View Logs
 6. Disable User                     16. Backup
 7. Enable User                      17. Restore
 8. Delete User                      18. Update
 9. Active Connections               19. Restart Services
10. Disconnect User                  20. Uninstall

 0. Exit
```

`ssh-ws` and the web panel call the exact same functions in
`manager/core/*.py` -- there is one source of truth for every rule (e.g.
"only accounts this project created can be deleted").

## Security notes

- The always-on manager and bridge processes run as an unprivileged
  service account; root access is limited to one allowlisted helper
  script reached through a single narrow sudoers rule.
- No secret (password, session token) is ever passed as a command-line
  argument to a subprocess -- everything sensitive goes over stdin.
- The firewall is always configured to allow your current SSH port
  *before* being enabled, in the same operation, so you cannot be locked
  out by turning it on.
- Full write-up, including specific findings from the pre-release review,
  in [docs/SECURITY.md](docs/SECURITY.md).

## Testing matrix

See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for the generated,
per-version results (installer, sshd, Nginx, WebSocket handshake, and
manager, each independently checked) and known limitations. Unit tests
(104 tests covering config/validation/user-lifecycle/backup-restore/
domain/firewall/logging/session-key-generation business logic),
`shellcheck` (0 findings across every shell script), and `ruff`
(0 findings) all run in CI
(`.github/workflows/ci.yml`) and locally via:

```bash
pip install -r manager/requirements.txt pytest ruff
pytest tests/unit
ruff check manager cli scripts tests
shellcheck install.sh update.sh uninstall.sh lib/*.sh scripts/*.sh
bash tests/integration/run-matrix.sh   # full Ubuntu matrix, needs Docker
```

## Known limitations

- **Not yet tested on a real cloud VPS** -- only inside systemd-capable
  Docker containers (see above). Cloud-provider-specific quirks
  (cloud-init, provider firewalls, kernel differences) are not covered by
  that testing.
- **Per-user bandwidth accounting is not implemented.** An accurate,
  non-fragile implementation would need per-connection `iptables`/`nftables`
  accounting keyed to dynamically-created users; rather than fake this
  with misleading numbers, the dashboard shows real, accurate data
  instead: active sessions, source IP, login time, and duration. Bandwidth
  accounting is a candidate future feature, not a silently-broken one.
- **Ubuntu 18.04**: its default `python3` (3.6) is too old to run this
  project's manager/CLI at all; `install.sh` detects this and installs
  `python3.8` from Ubuntu's own official archive for the venv
  specifically (verified working end-to-end, not just assumed). Its apt
  archives are also past standard EOL and frozen at that state, so
  `certbot`/`python3-certbot-nginx` in particular may still be outdated
  or unavailable there without Ubuntu Pro ESM. See
  [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).
- **UFW's `enable` step** could not be verified inside this project's own
  Docker-based test sandbox specifically (a missing kernel module in that
  container runtime -- `ufw allow`, the rule-syncing half, works and is
  tested); needs verification on a real VPS kernel. See
  [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).
- **arm64** is supported the same way as amd64 but has had less testing.

## Project structure

```
ssh-websocket-server/
├── install.sh / update.sh / uninstall.sh
├── manager/           Flask web panel + manager/core/ (shared business logic)
├── cli/                ssh_ws_cli.py (the ssh-ws command)
├── lib/                bash helpers shared by install/update/uninstall
├── scripts/             priv_helper.py (root helper) + install-time scripts
├── nginx/ systemd/       reference config / unit files (generated at install time)
├── tests/                unit (pytest) + integration (Docker matrix)
└── docs/                 SECURITY.md, CLIENTS.md, COMPATIBILITY.md
```

## License

MIT -- see [LICENSE](LICENSE). This project's own code depends on
permissively-licensed libraries (Flask, Werkzeug, Flask-WTF, WTForms,
Flask-Limiter, gunicorn -- BSD/MIT/Apache-2.0 family) plus **websockify**,
which is **LGPLv3**. websockify is installed as a separate, unmodified
package the installer runs as its own process (`python -m websockify`) --
this project does not import or link it into its own code, and the
administrator can swap in any other build of it, so LGPLv3's copyleft
terms are satisfied without imposing any obligation on this project's own
MIT-licensed code. See [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) for
the full audit. OpenSSH, Nginx, Certbot, Fail2ban and UFW are installed
from Ubuntu's own package archives, not bundled.

## Disclaimer

This is early-stage software (v0.1.0). Review [docs/SECURITY.md](docs/SECURITY.md)
and test in a non-production environment before exposing it to the
internet. No warranty is provided -- see [LICENSE](LICENSE).
