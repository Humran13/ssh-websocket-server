#!/usr/bin/env bash
# Input validation used during interactive install/config prompts. These
# intentionally mirror the regexes in manager/core/config.py and
# manager/core/users.py so a value accepted here is guaranteed to also be
# accepted by the Python side that ultimately enforces it again.

valid_port() {
    local p="$1"
    [[ "$p" =~ ^[0-9]+$ ]] || return 1
    (( p >= 1 && p <= 65535 ))
}

valid_ws_path() {
    local p="$1"
    [[ "$p" == /* ]] || return 1
    [[ "$p" == *".."* ]] && return 1
    [[ "$p" == *"//"* ]] && return 1
    [[ "$p" =~ ^/[a-zA-Z0-9._~/-]{1,127}$ ]]
}

valid_domain() {
    local d="$1"
    [[ ${#d} -gt 0 && ${#d} -le 253 ]] || return 1
    [[ "$d" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]]
}

valid_username() {
    local u="$1"
    [[ "$u" =~ ^[a-z][a-z0-9_-]{2,31}$ ]]
}

prompt_port() {
    # prompt_port <label> <default> -> echoes chosen port
    local label="$1" default="$2" value
    while true; do
        read -r -p "$label [$default]: " value
        value="${value:-$default}"
        if valid_port "$value"; then
            echo "$value"
            return 0
        fi
        log_warn "Invalid port: $value (must be 1-65535)"
    done
}

prompt_ws_path() {
    local label="$1" default="$2" value
    while true; do
        read -r -p "$label [$default]: " value
        value="${value:-$default}"
        if valid_ws_path "$value"; then
            echo "$value"
            return 0
        fi
        log_warn "Invalid WebSocket path: $value (must start with / and contain only safe characters)"
    done
}

prompt_domain() {
    local label="$1" value
    while true; do
        read -r -p "$label (leave blank for IP-only mode): " value
        if [[ -z "$value" ]]; then
            echo ""
            return 0
        fi
        if valid_domain "$value"; then
            echo "$value"
            return 0
        fi
        log_warn "Invalid domain: $value"
    done
}
