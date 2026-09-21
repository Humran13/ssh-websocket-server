#!/usr/bin/env bash
# Shared helpers sourced by install.sh, update.sh, uninstall.sh and the
# scripts/ directory. Not meant to be executed directly.
#
# Conventions used throughout this project's shell code:
#   - `set -euo pipefail` in every entry-point script.
#   - No secret (password, token) ever appears in a command line that
#     `ps`/history would capture -- pass via stdin or an env var instead.
#   - Every destructive step logs before acting, so install.log always
#     explains what happened even if a later step fails.

SSHWS_LOG_FILE="${SSHWS_LOG_FILE:-/var/log/ssh-websocket-server/install.log}"

sshws_log_init() {
    local dir
    dir="$(dirname "$SSHWS_LOG_FILE")"
    mkdir -p "$dir" 2>/dev/null || true
    touch "$SSHWS_LOG_FILE" 2>/dev/null || SSHWS_LOG_FILE="/dev/null"
}

_sshws_ts() { date -u '+%Y-%m-%d %H:%M:%S UTC'; }

log_info()  { printf '\033[36m[INFO]\033[0m  %s\n' "$*"; echo "$(_sshws_ts) [INFO] $*" >>"$SSHWS_LOG_FILE"; }
log_warn()  { printf '\033[33m[WARN]\033[0m  %s\n' "$*" >&2; echo "$(_sshws_ts) [WARN] $*" >>"$SSHWS_LOG_FILE"; }
log_error() { printf '\033[31m[ERROR]\033[0m %s\n' "$*" >&2; echo "$(_sshws_ts) [ERROR] $*" >>"$SSHWS_LOG_FILE"; }
log_ok()    { printf '\033[32m[OK]\033[0m    %s\n' "$*"; echo "$(_sshws_ts) [OK] $*" >>"$SSHWS_LOG_FILE"; }
log_step()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; echo "$(_sshws_ts) [STEP] $*" >>"$SSHWS_LOG_FILE"; }

die() {
    log_error "$*"
    exit 1
}

require_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        die "This command must be run as root (try: sudo $0)"
    fi
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

confirm() {
    # confirm "question" -- returns 0 (yes) / 1 (no). Auto-yes if
    # SSHWS_ASSUME_YES=1 (used by non-interactive / CI installs).
    local prompt="$1"
    if [[ "${SSHWS_ASSUME_YES:-0}" == "1" ]]; then
        return 0
    fi
    local reply
    read -r -p "$prompt [y/N] " reply || true
    [[ "$reply" =~ ^[Yy]$ ]]
}

port_in_use() {
    # port_in_use <port> -- returns 0 if something is already listening.
    local port="$1"
    if command_exists ss; then
        ss -H -ltn "sport = :${port}" 2>/dev/null | grep -q . && return 0
        ss -H -lun "sport = :${port}" 2>/dev/null | grep -q . && return 0
        return 1
    elif command_exists netstat; then
        netstat -ltn 2>/dev/null | awk '{print $4}' | grep -q ":${port}\$" && return 0
        return 1
    else
        # Fall back to a raw bind attempt via /dev/tcp (best-effort only).
        (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null && { exec 3>&-; return 0; }
        return 1
    fi
}

random_hex() {
    # random_hex <bytes> -- cryptographically random hex string.
    local n="${1:-16}"
    if command_exists openssl; then
        openssl rand -hex "$n"
    else
        head -c "$n" /dev/urandom | od -An -tx1 | tr -d ' \n'
    fi
}

backup_file() {
    # backup_file <path> -- copies path to path.bak-<timestamp> if it exists.
    local path="$1"
    if [[ -e "$path" ]]; then
        local ts
        ts="$(date -u '+%Y%m%d%H%M%S')"
        cp -a "$path" "${path}.bak-${ts}"
        log_info "Backed up $path -> ${path}.bak-${ts}"
    fi
}

sshws_venv_python() {
    echo "${SSHWS_ROOT:-/opt/ssh-websocket-server}/venv/bin/python3"
}
