# SSH user management: what "managed" means and why

## The safety rule

Only OS accounts that this project itself created -- tracked in the
`managed_users` SQLite table -- can ever be disabled, deleted, have their
password changed, or have their expiry/session-limit changed through the
panel, the CLI, or the privileged helper. This is enforced in two
independent places:

1. `manager/core/users.py` -- every mutating function calls
   `_require_managed(username)` first, which raises unless the username
   exists in `managed_users`.
2. `scripts/priv_helper.py::require_managed_account()` -- the root
   helper *itself* refuses to touch any account with `uid < 1000`, or
   any name in a hard-coded denylist (`root`, `sshws`, every standard
   Ubuntu system account), regardless of what the caller (even a
   compromised manager process) claims.

Layer 2 exists specifically so that a bug or compromise in layer 1 can't
turn into "delete root" or "lock out the service account" -- the root
helper is the last line of defense and does not trust its caller's
bookkeeping.

## Lifecycle

- **Create**: `useradd --create-home --shell /usr/sbin/nologin`. The
  `nologin` shell blocks interactive shell access while leaving SSH
  authentication and TCP forwarding (which is what actually carries
  WebSocket-tunneled SSH traffic) intact -- this is the standard pattern
  for "tunnel-only" SSH accounts.
- **Password**: set via `chpasswd`, reading `username:password` from
  **stdin**, never as a command-line argument.
- **Disable**: `usermod --lock` (disables password auth immediately) plus
  disconnecting any of that user's currently active sessions.
- **Enable**: `usermod --unlock`.
- **Delete**: requires explicit confirmation (the web UI requires
  re-typing the exact username; the CLI requires retyping it too) before
  `userdel --remove` runs.
- **Expiry**: `chage --expiredate`, in days-since-epoch, matching
  standard `/etc/shadow` semantics -- Ubuntu's own login machinery
  enforces it, not a custom check.
- **Session limit**: see [SESSION_LIMITS.md](SESSION_LIMITS.md).

## What's deliberately out of scope

Managing pre-existing SSH accounts that this project did not create is
intentionally unsupported from the panel/CLI -- both to keep the safety
rule above absolute, and because guessing at an existing account's
intended shell/permissions would be error-prone. Create a new managed
account instead.
