#!/usr/bin/env bash
# Updates an existing ssh-websocket-server install in place.
#   sudo /opt/ssh-websocket-server/update.sh
#   or:  ssh-ws  ->  Update
set -euo pipefail

SSHWS_ROOT="${SSHWS_ROOT:-/opt/ssh-websocket-server}"
SSHWS_REPO_REF="${SSHWS_REPO_REF:-main}"

if [[ ! -d "$SSHWS_ROOT" ]]; then
    echo "No install found at $SSHWS_ROOT. Nothing to update." >&2
    exit 1
fi

# shellcheck source=lib/common.sh
source "$SSHWS_ROOT/lib/common.sh"
SSHWS_LOG_FILE="/var/log/ssh-websocket-server/install.log"
sshws_log_init
require_root

VENV_PY="$SSHWS_ROOT/venv/bin/python3"
CURRENT_VERSION="$(cat "$SSHWS_ROOT/VERSION" 2>/dev/null || echo "0.0.0")"
log_step "Updating ssh-websocket-server (currently v$CURRENT_VERSION)"

log_step "Backing up current state before touching anything"
BACKUP_PATH="$(PYTHONPATH="$SSHWS_ROOT/manager" "$VENV_PY" -c \
    "from core import backup; print(backup.create_backup(actor='update.sh'))")"
log_ok "Pre-update backup: $BACKUP_PATH"

rollback() {
    log_error "Update failed -- rolling back to the pre-update backup."
    if [[ -n "${PREV_COMMIT:-}" && -d "$SSHWS_ROOT/.git" ]]; then
        git -C "$SSHWS_ROOT" checkout -q "$PREV_COMMIT" || true
    fi
    PYTHONPATH="$SSHWS_ROOT/manager" "$VENV_PY" -c \
        "from pathlib import Path; from core import backup; backup.restore_backup(Path('$BACKUP_PATH'))" || true
    "$VENV_PY" -m pip install -q -r "$SSHWS_ROOT/manager/requirements.txt" || true
    systemctl restart sshws-manager sshws-bridge nginx || true
    log_error "Rolled back. The pre-update backup is kept at: $BACKUP_PATH"
}

if [[ -d "$SSHWS_ROOT/.git" ]]; then
    PREV_COMMIT="$(git -C "$SSHWS_ROOT" rev-parse HEAD)"
    log_step "Fetching latest release ($SSHWS_REPO_REF)"
    trap rollback ERR
    git -C "$SSHWS_ROOT" fetch --depth 1 origin "$SSHWS_REPO_REF"
    git -C "$SSHWS_ROOT" checkout -q FETCH_HEAD -- . ':!/etc' ':!config.json' 2>/dev/null || \
        git -C "$SSHWS_ROOT" checkout -q FETCH_HEAD
else
    log_warn "$SSHWS_ROOT is not a git checkout (was it installed from a local copy?)." \
             "Skipping the code fetch step -- only dependencies/services will be refreshed."
    trap rollback ERR
fi

NEW_VERSION="$(cat "$SSHWS_ROOT/VERSION" 2>/dev/null || echo "$CURRENT_VERSION")"
log_info "New version: v$NEW_VERSION"

log_step "Updating Python dependencies"
"$VENV_PY" -m pip install -q --upgrade pip
"$VENV_PY" -m pip install -q -r "$SSHWS_ROOT/manager/requirements.txt"

log_step "Refreshing systemd units"
# Re-render units using the same values already on disk (install.sh's
# substitutions are idempotent -- we only need to refresh the template
# body, e.g. new hardening directives, not the environment-specific values).
CONFIG_JSON="$(PYTHONPATH="$SSHWS_ROOT/manager" "$VENV_PY" -c "import json; from core import config; print(json.dumps(config.load()))")"
SSH_PORT="$(echo "$CONFIG_JSON" | jq -r .ssh_port)"
BRIDGE_PORT="$(echo "$CONFIG_JSON" | jq -r .bridge_port)"
MANAGER_PORT="$(echo "$CONFIG_JSON" | jq -r .manager_port)"
for unit in sshws-bridge sshws-manager; do
    sed -e "s#SSHWS_VENV_PYTHON#$VENV_PY#g" \
        -e "s#SSHWS_INSTALL_ROOT#$SSHWS_ROOT#g" \
        -e "s#SSHWS_BRIDGE_BIND#127.0.0.1#g" \
        -e "s#SSHWS_BRIDGE_PORT#$BRIDGE_PORT#g" \
        -e "s#SSHWS_SSH_PORT#$SSH_PORT#g" \
        -e "s#SSHWS_MANAGER_BIND#0.0.0.0#g" \
        -e "s#SSHWS_MANAGER_PORT#$MANAGER_PORT#g" \
        "$SSHWS_ROOT/systemd/${unit}.service" > "/etc/systemd/system/${unit}.service"
done
systemctl daemon-reload

log_step "Running database migrations (if any)"
PYTHONPATH="$SSHWS_ROOT/manager" "$VENV_PY" -c "from core import db; db.init_db()"

log_step "Restarting services"
systemctl restart sshws-bridge sshws-manager
systemctl reload nginx || systemctl restart nginx

log_step "Running health checks"
HEALTH_JSON="$(PYTHONPATH="$SSHWS_ROOT/manager" "$VENV_PY" -c \
    "import json; from core import health; print(json.dumps(health.run_all()))")"
echo "$HEALTH_JSON" | jq .
if echo "$HEALTH_JSON" | jq -e 'to_entries | map(.value.ok) | all' >/dev/null; then
    trap - ERR
    log_ok "Update to v$NEW_VERSION complete. All health checks passed."
else
    log_error "One or more health checks failed after update."
    rollback
    trap - ERR
    exit 1
fi
