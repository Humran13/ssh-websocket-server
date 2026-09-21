#!/usr/bin/env bash
# Prints the post-install / `ssh-ws` connection-info summary.
# Usage: print_summary.sh <root> <venv-python>
set -euo pipefail
SSHWS_ROOT="${1:?install root required}"
VENV_PY="${2:?venv python path required}"

SUMMARY_JSON="$(PYTHONPATH="$SSHWS_ROOT/manager" "$VENV_PY" - <<'PYEOF'
import json
from core import config as config_mod, system_info, domain

cfg = config_mod.load()
print(json.dumps({
    "cfg": cfg,
    "hostname": system_info.hostname(),
    "public_ip": system_info.public_ip(),
    "cert": domain.certificate_status(),
    "services": {
        "sshd": system_info.service_status("ssh"),
        "bridge": system_info.service_status("sshws-bridge"),
        "nginx": system_info.service_status("nginx"),
        "manager": system_info.service_status("sshws-manager"),
    },
    "firewall": system_info.firewall_status(),
}))
PYEOF
)"

get() { echo "$SUMMARY_JSON" | jq -r "$1"; }

IP="$(get '.public_ip // "unknown"')"
HOSTNAME="$(get '.hostname')"
DOMAIN="$(get '.cfg.domain // empty')"
SSH_PORT="$(get '.cfg.ssh_port')"
WS_PORT="$(get '.cfg.ws_port')"
WSS_PORT="$(get '.cfg.wss_port')"
WS_ENABLED="$(get '.cfg.ws_enabled')"
WSS_ENABLED="$(get '.cfg.wss_enabled')"
WS_PATH="$(get '.cfg.ws_paths[0]')"
MANAGER_PORT="$(get '.cfg.manager_port')"
CERT_EXPIRES="$(get '.cert.expires // "not configured"')"
SSHD_STATUS="$(get '.services.sshd')"
BRIDGE_STATUS="$(get '.services.bridge')"
NGINX_STATUS="$(get '.services.nginx')"
MANAGER_STATUS="$(get '.services.manager')"
FIREWALL_STATUS="$(get '.firewall')"

HOST_FOR_URL="${DOMAIN:-$IP}"

cat <<EOF

==================================================================
 SSH WebSocket Server -- installation summary
==================================================================
 Hostname:          $HOSTNAME
 Public IP:         $IP
 Domain:            ${DOMAIN:-"(none -- IP mode)"}
 SSH port:          $SSH_PORT

 Direct SSH
 -------------------------
 Host: $HOST_FOR_URL
 Port: $SSH_PORT

EOF

if [[ "$WS_ENABLED" == "true" ]]; then
cat <<EOF
 WebSocket (ws://)
 -------------------------
 URL:  ws://$HOST_FOR_URL:$WS_PORT$WS_PATH
 Port: $WS_PORT
 Path: $WS_PATH

EOF
fi

if [[ "$WSS_ENABLED" == "true" ]]; then
cat <<EOF
 Secure WebSocket (wss://)
 -------------------------
 URL:      wss://$HOST_FOR_URL:$WSS_PORT$WS_PATH
 Port:     $WSS_PORT
 Path:     $WS_PATH
 TLS:      Enabled (certificate expires: $CERT_EXPIRES)

EOF
fi

cat <<EOF
 Management panel:  http://$IP:$MANAGER_PORT/  (and via Nginx at $HOST_FOR_URL$(get '.cfg.manager_path'))
 CLI command:       ssh-ws

 Service status
 -------------------------
 sshd:      $SSHD_STATUS
 bridge:    $BRIDGE_STATUS
 nginx:     $NGINX_STATUS
 manager:   $MANAGER_STATUS
 firewall:  $FIREWALL_STATUS
 SSL:       ${CERT_EXPIRES}

 Note: the ws:// / wss:// URLs above are this server's WebSocket
 endpoints, not a ready-to-paste OpenSSH connection string -- see
 docs/CLIENTS.md for how a WebSocket-capable SSH client uses them.
==================================================================
EOF
