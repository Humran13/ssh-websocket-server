#!/usr/bin/env bash
# OS / architecture detection and support-matrix checks.
#
# Researched support notes (see docs/COMPATIBILITY.md for the full write-up
# and how each one was verified):
#   - 18.04 (bionic) is long past standard EOL. Its apt archives are frozen
#     and some packages (certbot in particular) are old/unavailable without
#     Ubuntu Pro ESM. The installer still attempts it and clearly reports
#     what could not be installed rather than pretending it fully works.
#   - 20.04 (focal) / 22.04 (jammy) / 24.04 (noble) all have the packages
#     this project needs (openssh-server, nginx, python3-venv, ufw,
#     fail2ban, certbot + python3-certbot-nginx) in the default archives.
#   - 26.04 (as the newest LTS at write time) is supported the same way as
#     22.04/24.04; if a required package is genuinely missing on a given
#     mirror the installer fails that step loudly instead of pretending.

SSHWS_SUPPORTED_VERSIONS=("18.04" "20.04" "22.04" "24.04" "26.04")

os_detect() {
    if [[ ! -f /etc/os-release ]]; then
        die "Cannot detect OS: /etc/os-release not found. This installer supports Ubuntu only."
    fi
    # shellcheck disable=SC1091
    source /etc/os-release
    SSHWS_OS_ID="${ID:-unknown}"
    SSHWS_OS_VERSION="${VERSION_ID:-unknown}"
    SSHWS_OS_CODENAME="${VERSION_CODENAME:-unknown}"
    SSHWS_OS_PRETTY="${PRETTY_NAME:-unknown}"

    if [[ "$SSHWS_OS_ID" != "ubuntu" ]]; then
        die "Unsupported distribution '$SSHWS_OS_ID'. This installer supports Ubuntu only (detected: $SSHWS_OS_PRETTY)."
    fi
}

os_is_supported_version() {
    local v
    for v in "${SSHWS_SUPPORTED_VERSIONS[@]}"; do
        [[ "$v" == "$SSHWS_OS_VERSION" ]] && return 0
    done
    return 1
}

os_check_supported() {
    os_detect
    log_info "Detected: $SSHWS_OS_PRETTY ($SSHWS_OS_CODENAME)"
    if ! os_is_supported_version; then
        log_warn "Ubuntu $SSHWS_OS_VERSION is not in the tested support matrix (${SSHWS_SUPPORTED_VERSIONS[*]})."
        if ! confirm "Continue anyway on an unsupported/untested Ubuntu version?"; then
            die "Aborted: unsupported Ubuntu version."
        fi
    fi
    if [[ "$SSHWS_OS_VERSION" == "18.04" ]]; then
        log_warn "Ubuntu 18.04 is past standard EOL. Some packages (notably certbot) may be" \
                 "outdated or unavailable on the default archives without Ubuntu Pro ESM."
        log_warn "The installer will continue and report exactly what could and could not be installed."
    fi
}

arch_detect() {
    SSHWS_ARCH_RAW="$(uname -m)"
    case "$SSHWS_ARCH_RAW" in
        x86_64|amd64) SSHWS_ARCH="amd64" ;;
        aarch64|arm64) SSHWS_ARCH="arm64" ;;
        *) SSHWS_ARCH="unsupported" ;;
    esac
}

arch_check_supported() {
    arch_detect
    log_info "Detected architecture: $SSHWS_ARCH_RAW ($SSHWS_ARCH)"
    case "$SSHWS_ARCH" in
        amd64) ;;
        arm64)
            log_warn "arm64 is supported on a best-effort basis (all dependencies used here" \
                     "publish arm64 builds, but it receives less testing than amd64)."
            ;;
        *)
            die "Unsupported CPU architecture: $SSHWS_ARCH_RAW. This project supports amd64 and arm64."
            ;;
    esac
}
