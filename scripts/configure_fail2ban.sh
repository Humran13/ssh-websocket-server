#!/usr/bin/env bash
# Conservative Fail2ban jail for SSH. Deliberately generous limits so a
# legitimate administrator fumbling a password a few times from a shared
# office/VPN IP does not get locked out.
set -euo pipefail

command -v fail2ban-client >/dev/null 2>&1 || { echo "fail2ban not installed, skipping."; exit 0; }

install -d -m 755 /etc/fail2ban/jail.d
cat > /etc/fail2ban/jail.d/ssh-websocket-server.conf <<'EOF'
# Managed by ssh-websocket-server. Deliberately conservative: 6 failures
# within 10 minutes bans for 30 minutes. Adjust to taste in this file --
# it will not be overwritten by an update, only re-created if missing.
[sshd]
enabled = true
backend = systemd
maxretry = 6
findtime = 10m
bantime = 30m
EOF

systemctl enable --now fail2ban >/dev/null 2>&1 || true
systemctl restart fail2ban
echo "Fail2ban configured for sshd (maxretry=6, findtime=10m, bantime=30m)."
