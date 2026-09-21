# Concurrent session limits

Enforced with the standard Linux `pam_limits` mechanism, not a
custom/fake counter.

When a per-user session limit is set (Add/Edit user -> "Max concurrent
sessions"), `scripts/priv_helper.py::action_user_set_max_sessions` writes
a line to `/etc/security/limits.d/90-ssh-websocket-server.conf`:

```
<username> hard maxlogins <N>
```

This file is entirely regenerated (not appended to indefinitely) each
time any managed user's limit changes, so it never accumulates stale
entries.

`pam_limits.so` -- already enabled in sshd's PAM stack on stock Ubuntu
(`/etc/pam.d/sshd` includes `session required pam_limits.so`) -- reads
this file and refuses a new login once a user has `N` sessions already
registered in `utmp`. Because both direct-SSH and WebSocket-tunneled
connections terminate at the same local `sshd`, which handles both
through the identical PAM session stack, the limit applies equally to
both -- there is no separate code path to keep in sync.

"Unlimited" (the default) simply means no line is written for that user;
removing a previously-set limit removes the line rather than writing a
very large number.
