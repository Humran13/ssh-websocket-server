# Fail2ban configuration

`scripts/configure_fail2ban.sh` writes one conservative jail,
`/etc/fail2ban/jail.d/ssh-websocket-server.conf`:

```ini
[sshd]
enabled = true
backend = systemd
maxretry = 6
findtime = 10m
bantime = 30m
```

Deliberately generous: 6 failed attempts within 10 minutes bans the
source IP for 30 minutes. This is meant to slow down credential
guessing without locking out an administrator who fumbles a password a
couple of times from a shared office/VPN egress IP. `backend = systemd`
reads sshd's authentication log directly from the systemd journal, which
is how sshd logs on every supported Ubuntu version here (no
`/var/log/auth.log` dependency, which varies by syslog configuration).

This file is not overwritten by `update.sh` if it already exists --
customize it freely; it is only created if missing.

Since the WebSocket bridge forwards to the same local sshd, failed
authentication attempts made over `ws://`/`wss://` are logged and count
toward the ban the same way direct-SSH attempts do.
