# Architecture

## Request flow

```
Client
  │
  ├─ direct SSH (any port, default 22) ───────────────────────► sshd
  │
  └─ ws:// or wss:// (WebSocket) ──► Nginx ──► websockify (bridge) ──► sshd
                                      │              │
                              TLS termination    127.0.0.1-only,
                              WS upgrade proxy   unprivileged (sshws)
```

Both paths terminate at the same local `sshd` -- WebSocket is a transport
wrapper, not a separate authentication system. See
[CLIENTS.md](CLIENTS.md) for what that means for connecting clients.

## Why websockify

A small, mature, actively-maintained library (the WebSocket↔TCP bridge
behind noVNC) rather than a hand-rolled proxy. It does exactly one thing
-- bridge a WebSocket connection to a plain TCP service -- which is
exactly what's needed here. Installed pinned (`websockify==0.11.0`) into
the project's own venv, run as the unprivileged `sshws` account, bound to
`127.0.0.1` only (Nginx is the only thing that talks to it directly; it
is never exposed on a public interface itself).

## Privilege boundary

See [SECURITY.md](SECURITY.md) for the full design. In one sentence: the
only process that ever runs as root is `scripts/priv_helper.py`, invoked
through one sudoers rule with no wildcard arguments, reading its action
and arguments as JSON from stdin (never argv), with every action
allowlisted and every input validated.

## Why Flask + SQLite (not a bigger framework)

The panel's job is small: an admin login, a handful of CRUD-ish pages
over SSH user metadata, and forms that call into `manager/core/*.py`.
Flask + server-rendered Jinja templates + SQLite is enough to do that
cleanly without pulling in a SPA build step, an ORM migration framework,
or a separate database server the installer would need to stand up.
SQLite here only ever stores **manager metadata** (admin accounts, which
OS accounts this project manages, an audit log) -- SSH authentication
itself always lives in the real `/etc/passwd`/`/etc/shadow`, so there is
no risk of the two drifting into an inconsistent, security-relevant state.

## Why one shared `core` package instead of two implementations

The spec calls for the CLI and web panel to use "the same underlying
management logic wherever practical." Concretely: `manager/core/users.py`
has exactly one `delete_user()` function, with exactly one place that
enforces "only project-managed, `uid >= 1000` accounts can be deleted,
and only with explicit confirmation." Both `manager/routes_users.py`
(Flask) and `cli/ssh_ws_cli.py` call it. A bug fix or a new safety rule
there is automatically correct in both interfaces; there is no second
copy that could drift.

## Config format

A single JSON file, `/etc/ssh-websocket-server/config.json`, is the
source of truth for ports, WebSocket paths, and domain/SSL state
(`manager/core/config.py`). It is validated on every write (port range,
no port collisions among the ports actually in use, WS path safety,
domain syntax) -- there is no way to persist an invalid combination
through the normal API, whether the caller is the installer, the CLI, or
the web panel.
