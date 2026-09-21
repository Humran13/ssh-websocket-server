#!/usr/bin/env bash
# Removes ssh-websocket-server. Never touches normal SSH access, unrelated
# Nginx sites, or SSH accounts this project did not create (unless you
# explicitly opt into removing managed accounts too).
set -euo pipefail

SSHWS_ROOT="${SSHWS_ROOT:-/opt/ssh-websocket-server}"
REMOVE_USERS="false"
ASSUME_YES="${SSHWS_ASSUME_YES:-0}"

for arg in "$@"; do
    case "$arg" in
        --remove-managed-users) REMOVE_USERS="true" ;;
        --yes) ASSUME_YES=1 ;;
    esac
done

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This must be run as root." >&2
    exit 1
fi

if [[ -f "$SSHWS_ROOT/lib/common.sh" ]]; then
    # shellcheck source=lib/common.sh
    source "$SSHWS_ROOT/lib/common.sh"
else
    log_info() { echo "[INFO] $*"; }
    log_warn() { echo "[WARN] $*" >&2; }
    log_ok()   { echo "[OK] $*"; }
    confirm() {
        [[ "$ASSUME_YES" == "1" ]] && return 0
        local reply; read -r -p "$1 [y/N] " reply || true
        [[ "$reply" =~ ^[Yy]$ ]]
    }
fi
SSHWS_LOG_FILE="/var/log/ssh-websocket-server/install.log"
sshws_log_init 2>/dev/null || true

cat <<EOF
This will remove ssh-websocket-server:
  - systemd services: sshws-bridge, sshws-manager
  - Nginx site config for this project (other sites are left untouched)
  - sudoers rule for the privileged helper
  - /usr/local/bin/ssh-ws
  - $SSHWS_ROOT (application files and Python venv)
  - /etc/ssh-websocket-server, /var/lib/ssh-websocket-server, /var/log/ssh-websocket-server
  - The 'sshws' service account

It will NOT remove:
  - OpenSSH itself, or your ability to SSH into this server directly
  - Any SSH user accounts this project created$( [[ "$REMOVE_USERS" == "true" ]] && echo " (unless you continue -- --remove-managed-users was passed)" )
  - Fail2ban or UFW themselves (only this project's jail/rules are removed)
  - Any other Nginx site
EOF

if [[ "$ASSUME_YES" != "1" ]] && ! confirm "Continue?"; then
    echo "Aborted."
    exit 0
fi

log_info "Stopping services"
systemctl stop sshws-bridge sshws-manager 2>/dev/null || true
systemctl disable sshws-bridge sshws-manager 2>/dev/null || true
rm -f /etc/systemd/system/sshws-bridge.service /etc/systemd/system/sshws-manager.service
systemctl daemon-reload

log_info "Removing Nginx site"
rm -f /etc/nginx/sites-enabled/ssh-websocket-server.conf /etc/nginx/sites-available/ssh-websocket-server.conf
if compgen -G "/etc/nginx/sites-available/default.bak-*" >/dev/null 2>&1; then
    log_warn "A backup of Nginx's original default site exists at /etc/nginx/sites-available/default.bak-* -- restore it manually with sites-enabled symlink if you want the stock page back."
fi
systemctl reload nginx 2>/dev/null || true

log_info "Removing Fail2ban jail"
rm -f /etc/fail2ban/jail.d/ssh-websocket-server.conf
systemctl restart fail2ban 2>/dev/null || true

log_info "Removing sudoers rule"
rm -f /etc/sudoers.d/ssh-websocket-server

log_info "Removing CLI"
rm -f /usr/local/bin/ssh-ws

if [[ "$REMOVE_USERS" == "true" && -f "$SSHWS_ROOT/manager/core/db.py" ]]; then
    log_warn "Removing all managed SSH user accounts (explicitly requested)..."
    VENV_PY="$SSHWS_ROOT/venv/bin/python3"
    if [[ -x "$VENV_PY" ]]; then
        PYTHONPATH="$SSHWS_ROOT/manager" "$VENV_PY" -c "
from core import users
for u in users.list_users():
    try:
        users.delete_user(u.username, 'uninstall.sh', confirm=True)
        print('deleted', u.username)
    except Exception as exc:
        print('failed to delete', u.username, exc)
"
    fi
fi

log_info "Removing application and data directories"
rm -rf "$SSHWS_ROOT"
rm -rf /etc/ssh-websocket-server /var/lib/ssh-websocket-server
mv /var/log/ssh-websocket-server "/var/log/ssh-websocket-server.removed-$(date -u +%Y%m%d%H%M%S)" 2>/dev/null || \
    rm -rf /var/log/ssh-websocket-server

if id sshws >/dev/null 2>&1; then
    userdel sshws 2>/dev/null || log_warn "Could not remove the 'sshws' system account (it may still own files)."
fi

log_ok "ssh-websocket-server has been uninstalled. OpenSSH and your existing SSH access are untouched."
