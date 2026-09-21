#!/usr/bin/env bash
# ssh-websocket-server installer.
#
#   bash <(curl -Ls https://raw.githubusercontent.com/Humran13/ssh-websocket-server/main/install.sh)
#
# Safe to re-run: existing configuration is preserved unless you explicitly
# choose to change it, and every config file this script touches is backed
# up before being overwritten. See README.md and docs/ for details.
set -euo pipefail

SSHWS_REPO_URL="${SSHWS_REPO_URL:-https://github.com/Humran13/ssh-websocket-server.git}"
SSHWS_REPO_REF="${SSHWS_REPO_REF:-main}"
SSHWS_ROOT="${SSHWS_ROOT:-/opt/ssh-websocket-server}"

# ---------------------------------------------------------------------------
# Bootstrap: figure out whether we're running from a real checkout (has a
# sibling lib/ directory -- true both for local/dev runs and for the
# re-exec below) or as a bare stream from `bash <(curl ...)`, in which case
# there is no "next to this file" to speak of and we must fetch a real
# checkout first.
# ---------------------------------------------------------------------------
_sshws_script_dir() {
    local src="${BASH_SOURCE[0]}"
    if [[ -f "$src" ]]; then
        cd "$(dirname "$src")" && pwd
    else
        echo ""
    fi
}

SCRIPT_DIR="$(_sshws_script_dir)"

if [[ -z "$SCRIPT_DIR" || ! -f "$SCRIPT_DIR/lib/common.sh" ]]; then
    # Running as `bash <(curl ...)` (or any other case where we can't see
    # our own siblings). Fetch a real checkout and re-exec from there.
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        echo "This installer must be run as root (try: sudo bash <(curl -Ls ...))." >&2
        exit 1
    fi
    if ! command -v git >/dev/null 2>&1; then
        echo "==> Installing git (required to fetch the project)..."
        apt-get update -qq
        apt-get install -y -qq git ca-certificates
    fi
    echo "==> Fetching ssh-websocket-server ($SSHWS_REPO_REF) into $SSHWS_ROOT ..."
    if [[ -d "$SSHWS_ROOT/.git" ]]; then
        git -C "$SSHWS_ROOT" fetch --depth 1 origin "$SSHWS_REPO_REF"
        git -C "$SSHWS_ROOT" checkout -q FETCH_HEAD
    else
        mkdir -p "$SSHWS_ROOT"
        git clone --depth 1 --branch "$SSHWS_REPO_REF" "$SSHWS_REPO_URL" "$SSHWS_ROOT"
    fi
    exec bash "$SSHWS_ROOT/install.sh" "$@"
fi

# ---------------------------------------------------------------------------
# Real installer body (we now have a full checkout at $SCRIPT_DIR).
# ---------------------------------------------------------------------------
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=lib/os-detect.sh
source "$SCRIPT_DIR/lib/os-detect.sh"
# shellcheck source=lib/validate.sh
source "$SCRIPT_DIR/lib/validate.sh"

SSHWS_LOG_FILE="/var/log/ssh-websocket-server/install.log"
sshws_log_init

SSHWS_SERVICE_USER="sshws"
DOMAIN=""
SSH_PORT=""
WS_PORT="80"
WSS_PORT="443"
BRIDGE_PORT="8765"
MANAGER_PORT="8088"
WS_PATHS=("/ssh")
ENABLE_FIREWALL="ask"
ISSUE_CERT="ask"
CERT_EMAIL=""
ADMIN_USERNAME=""
ADMIN_PASSWORD=""

usage() {
    cat <<'EOF'
Usage: install.sh [options]

  --domain=HOST          Configure domain + WSS mode (Let's Encrypt certificate)
  --ssh-port=PORT         SSH port to report/use (default: current sshd port, usually 22)
  --ws-port=PORT          Public WebSocket (ws://) port (default: 80)
  --wss-port=PORT         Public secure WebSocket (wss://) port (default: 443)
  --ws-path=PATH          WebSocket path; may be given multiple times (default: /ssh)
  --manager-port=PORT     Web panel port (default: 8088)
  --admin-username=NAME   Create the initial panel admin non-interactively
  --admin-password=PASS   Password for --admin-username (avoid on shared shells; prefer prompts)
  --yes                   Assume "yes" to all confirmations (non-interactive)
  --skip-firewall         Do not touch UFW
  --skip-ssl              Do not attempt to request a Let's Encrypt certificate
  -h, --help              Show this help
EOF
}

for arg in "$@"; do
    case "$arg" in
        --domain=*) DOMAIN="${arg#*=}" ;;
        --ssh-port=*) SSH_PORT="${arg#*=}" ;;
        --ws-port=*) WS_PORT="${arg#*=}" ;;
        --wss-port=*) WSS_PORT="${arg#*=}" ;;
        --ws-path=*) WS_PATHS+=("${arg#*=}") ;;
        --manager-port=*) MANAGER_PORT="${arg#*=}" ;;
        --admin-username=*) ADMIN_USERNAME="${arg#*=}" ;;
        --admin-password=*) ADMIN_PASSWORD="${arg#*=}" ;;
        --yes) export SSHWS_ASSUME_YES=1 ;;
        --skip-firewall) ENABLE_FIREWALL="false" ;;
        --skip-ssl) ISSUE_CERT="false" ;;
        -h|--help) usage; exit 0 ;;
        *) log_warn "Unknown option: $arg" ;;
    esac
done
if [[ ${#WS_PATHS[@]} -gt 1 ]]; then
    WS_PATHS=("${WS_PATHS[@]:1}")  # drop the seeded default if the user gave their own
fi

log_step "SSH WebSocket Server installer"
require_root

log_step "Detecting operating system and architecture"
os_check_supported
arch_check_supported

log_step "Checking required tools"
# curl/dnsutils etc. are installed a few steps down as part of the normal
# dependency list if missing (a bare Ubuntu image -- cloud or container --
# does not always ship curl); systemd is the one thing we cannot fix by
# installing a package, so it is the only hard pre-flight requirement.
command_exists systemctl || die "Required tool not found: systemctl (this installer requires a systemd-based Ubuntu system)"

if [[ -z "$SSH_PORT" ]]; then
    if [[ -f /etc/ssh/sshd_config ]]; then
        SSH_PORT="$(grep -Eio '^[[:space:]]*Port[[:space:]]+[0-9]+' /etc/ssh/sshd_config | tail -n1 | grep -Eo '[0-9]+' || true)"
    fi
    SSH_PORT="${SSH_PORT:-22}"
fi
valid_port "$SSH_PORT" || die "Invalid SSH port: $SSH_PORT"
log_info "Using SSH port: $SSH_PORT (existing OpenSSH configuration is left untouched)"

if [[ -z "${DOMAIN}" && "${SSHWS_ASSUME_YES:-0}" != "1" ]]; then
    DOMAIN="$(prompt_domain "Domain for WSS (e.g. vpn.example.com)")"
fi
if [[ -n "$DOMAIN" ]]; then
    valid_domain "$DOMAIN" || die "Invalid domain: $DOMAIN"
fi

if [[ ${#WS_PATHS[@]} -eq 0 ]]; then
    WS_PATHS=("/ssh")
fi
for p in "${WS_PATHS[@]}"; do
    valid_ws_path "$p" || die "Invalid WebSocket path: $p"
done

log_step "Checking port availability"
for port_info in "WebSocket:$WS_PORT" "Manager:$MANAGER_PORT" "Bridge:$BRIDGE_PORT"; do
    name="${port_info%%:*}"; port="${port_info##*:}"
    if port_in_use "$port"; then
        die "$name port $port is already in use. Re-run with a different --*-port option."
    fi
done
if [[ -n "$DOMAIN" ]] && port_in_use "$WSS_PORT"; then
    die "WSS port $WSS_PORT is already in use."
fi
log_ok "Required ports are free."

log_step "Installing system dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
PKGS=(openssh-server nginx python3 python3-venv python3-pip python3-dev
      sqlite3 ufw fail2ban curl git jq openssl ca-certificates dnsutils build-essential)
if [[ -n "$DOMAIN" && "$ISSUE_CERT" != "false" ]]; then
    PKGS+=(certbot python3-certbot-nginx)
fi
if ! apt-get install -y -qq "${PKGS[@]}"; then
    log_warn "Some packages failed to install (this is expected on EOL releases like 18.04" \
             "without Ubuntu Pro ESM). Continuing with what is available."
fi
for required in openssh-server nginx python3; do
    dpkg -s "$required" >/dev/null 2>&1 || die "Required package failed to install: $required"
done
log_ok "System dependencies installed."

log_step "Checking network/DNS"
if command_exists curl && curl -fsS --max-time 5 https://1.1.1.1 >/dev/null 2>&1; then
    log_ok "Outbound internet connectivity looks fine."
else
    log_warn "Could not reach the internet. Package installs above may have partially failed," \
             "and Let's Encrypt certificate requests will not work until connectivity is restored."
fi
if [[ -n "$DOMAIN" ]]; then
    if command_exists getent && getent hosts "$DOMAIN" >/dev/null 2>&1; then
        log_ok "Domain '$DOMAIN' resolves."
    else
        log_warn "Domain '$DOMAIN' does not currently resolve. Certificate issuance will likely fail" \
                 "until DNS is pointed at this server; WS/IP mode will still work."
    fi
fi

log_step "Creating service account"
if ! id "$SSHWS_SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SSHWS_SERVICE_USER"
    log_ok "Created system user '$SSHWS_SERVICE_USER'."
else
    log_info "Service user '$SSHWS_SERVICE_USER' already exists."
fi

log_step "Installing application files to $SSHWS_ROOT"
if [[ "$SCRIPT_DIR" != "$SSHWS_ROOT" ]]; then
    mkdir -p "$SSHWS_ROOT"
    rsync -a --delete \
        --exclude '.git' --exclude 'tests' --exclude '.devvenv' --exclude '.github' \
        "$SCRIPT_DIR"/ "$SSHWS_ROOT"/ 2>/dev/null || \
    cp -a "$SCRIPT_DIR"/. "$SSHWS_ROOT"/
fi
mkdir -p /etc/ssh-websocket-server /var/lib/ssh-websocket-server /var/log/ssh-websocket-server
# Owned directly by the service account (not root:sshws group-readable) --
# the manager process writes its own secret key, config, and database
# here at runtime with no privilege elevation, since none of that needs
# root. Root can always read/write regardless of these bits, which is all
# the privileged helper needs.
chown -R "$SSHWS_SERVICE_USER":"$SSHWS_SERVICE_USER" /etc/ssh-websocket-server /var/lib/ssh-websocket-server /var/log/ssh-websocket-server
chmod 700 /etc/ssh-websocket-server /var/lib/ssh-websocket-server /var/log/ssh-websocket-server
log_ok "Files installed."

log_step "Setting up Python virtual environment"
# manager/core/*.py uses `from __future__ import annotations` (PEP 563),
# which requires Python >= 3.7 to even parse, and this project's pinned
# Flask/Werkzeug versions require >= 3.8. Ubuntu 18.04's default `python3`
# is 3.6 -- too old either way. Rather than silently fail deep into the
# install, or add a third-party PPA, Ubuntu 18.04's own official archive
# already carries a usable python3.8 (+ -venv/-dev/-distutils) package;
# use that instead of the system default when it's too old. Verified
# directly (not assumed): `python3.8-venv` alone is not sufficient on
# 18.04 -- ensurepip fails without `python3.8-distutils` also installed.
PYTHON_BIN="python3"
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    log_warn "System python3 ($(python3 --version 2>&1)) is older than the 3.8 this project" \
             "requires. Installing python3.8 from Ubuntu's own archive for the venv only" \
             "(the system python3 / any other software using it is left untouched)."
    if apt-get install -y -qq python3.8 python3.8-venv python3.8-dev python3.8-distutils; then
        PYTHON_BIN="python3.8"
    else
        die "python3 is too old ($(python3 --version 2>&1)) and python3.8 is not available" \
            "from this system's package archive. This Ubuntu release cannot run the manager/CLI;" \
            "see docs/COMPATIBILITY.md."
    fi
fi

VENV_DIR="$SSHWS_ROOT/venv"
if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
VENV_PY="$VENV_DIR/bin/python3"
"$VENV_PY" -m pip install -q --upgrade pip
"$VENV_PY" -m pip install -q -r "$SSHWS_ROOT/manager/requirements.txt"
"$VENV_PY" -m pip install -q "websockify==0.11.0"
log_ok "Virtual environment ready: $VENV_PY"

log_step "Installing sudoers rule for the privileged helper"
SUDOERS_SRC="$SSHWS_ROOT/scripts/sshws.sudoers"
SUDOERS_DST="/etc/sudoers.d/ssh-websocket-server"
sed -e "s#SSHWS_VENV_PYTHON#$VENV_PY#g" -e "s#SSHWS_INSTALL_ROOT#$SSHWS_ROOT#g" \
    "$SUDOERS_SRC" > /tmp/sshws.sudoers.new
visudo -cf /tmp/sshws.sudoers.new || die "Generated sudoers file failed validation; aborting before install."
install -m 0440 -o root -g root /tmp/sshws.sudoers.new "$SUDOERS_DST"
rm -f /tmp/sshws.sudoers.new
log_ok "Sudoers rule installed: $SUDOERS_DST"

log_step "Installing systemd units"
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
log_ok "systemd units installed."

log_step "Preparing Nginx"
if [[ -e /etc/nginx/sites-enabled/default ]]; then
    # Ubuntu/Debian's stock nginx package always ships this exact comment
    # immediately above the default server block; its presence is a much
    # more reliable "this hasn't been hand-edited" signal than page content
    # (which lives in /var/www/html, not this config file, and so says
    # nothing about whether the config itself was customized).
    if grep -q "^# Default server configuration" /etc/nginx/sites-available/default 2>/dev/null; then
        backup_file /etc/nginx/sites-available/default
        rm -f /etc/nginx/sites-enabled/default
        log_info "Disabled Nginx's untouched stock default site so this project's IP-mode" \
                 "site can serve as the default server on port $WS_PORT. Its config file is" \
                 "kept (backed up) at /etc/nginx/sites-available/default, not deleted."
    else
        log_warn "An existing, apparently customized Nginx default site is enabled." \
                 "Leaving it in place -- IP-only WebSocket access may not work until you" \
                 "resolve the conflict manually (see docs/CLIENTS.md)."
    fi
fi

if [[ -z "$ISSUE_CERT" || "$ISSUE_CERT" == "ask" ]]; then
    if [[ -n "$DOMAIN" ]]; then
        if confirm "Request a Let's Encrypt certificate for $DOMAIN now?"; then
            ISSUE_CERT="true"
        else
            ISSUE_CERT="false"
        fi
    else
        ISSUE_CERT="false"
    fi
fi

if [[ "$ENABLE_FIREWALL" == "ask" ]]; then
    if confirm "Enable UFW firewall (SSH/$WS_PORT/$WSS_PORT/$MANAGER_PORT will be allowed first)?"; then
        ENABLE_FIREWALL="true"
    else
        ENABLE_FIREWALL="false"
    fi
fi

if [[ -z "$ADMIN_USERNAME" && "${SSHWS_ASSUME_YES:-0}" != "1" ]]; then
    read -r -p "Web panel admin username [admin]: " ADMIN_USERNAME
    ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
    while [[ -z "$ADMIN_PASSWORD" || ${#ADMIN_PASSWORD} -lt 12 ]]; do
        read -r -s -p "Web panel admin password (12+ chars): " ADMIN_PASSWORD; echo
    done
fi

log_step "Applying configuration"
WS_PATH_ARGS=()
for p in "${WS_PATHS[@]}"; do WS_PATH_ARGS+=(--ws-path "$p"); done

CONFIGURE_ARGS=(
    --ssh-port "$SSH_PORT" --ws-port "$WS_PORT" --wss-port "$WSS_PORT"
    --bridge-port "$BRIDGE_PORT" --manager-port "$MANAGER_PORT"
    "${WS_PATH_ARGS[@]}" --domain "$DOMAIN"
    --enable-firewall "$ENABLE_FIREWALL" --issue-cert "$ISSUE_CERT" --cert-email "$CERT_EMAIL"
)
if [[ -n "$ADMIN_USERNAME" && -n "$ADMIN_PASSWORD" ]]; then
    CONFIGURE_ARGS+=(--admin-username "$ADMIN_USERNAME" --admin-password "$ADMIN_PASSWORD")
fi

CONFIGURE_OUTPUT="$("$VENV_PY" "$SSHWS_ROOT/scripts/post_install_configure.py" "${CONFIGURE_ARGS[@]}")" \
    || log_warn "post-install configuration reported problems -- see details below."
echo "$CONFIGURE_OUTPUT" | tee -a "$SSHWS_LOG_FILE" >/dev/null
echo "$CONFIGURE_OUTPUT" | jq -r \
    '.steps[] | "  " + (if .ok then "[OK]  " else "[FAIL]" end) + " " + .name + (if .ok then "" else ": " + (.detail | tostring) end)' \
    2>/dev/null || echo "$CONFIGURE_OUTPUT"
unset ADMIN_PASSWORD

# post_install_configure.py just ran as root and may have created new
# files under these directories (config.json, the secret key, the
# SQLite db, ...). A file root creates always defaults to root:root
# ownership regardless of which user owns its parent directory, so even
# though these directories were already chowned to the service account
# above, anything newly created here still needs re-owning -- verified
# directly: the manager (running as sshws) hit a PermissionError reading
# a root-owned secret key file before this line was added. Recursive and
# unconditional is deliberate: patching each file creator individually
# proved easy to miss one; this can't miss any of them.
chown -R "$SSHWS_SERVICE_USER":"$SSHWS_SERVICE_USER" /etc/ssh-websocket-server /var/lib/ssh-websocket-server

log_step "Starting services"
systemctl enable --now ssh >/dev/null 2>&1 || true
systemctl enable --now nginx
systemctl enable --now sshws-bridge
systemctl enable --now sshws-manager
systemctl enable --now fail2ban || log_warn "fail2ban did not start; check 'systemctl status fail2ban'."
log_ok "Services started."

log_step "Configuring Fail2ban for SSH"
# Invoked via `bash` explicitly rather than relying on the executable bit:
# git only preserves that bit when it was set at commit time, and a
# clone (as opposed to a same-filesystem copy) is the one path that
# actually enforces it -- this must not depend on it.
bash "$SCRIPT_DIR/scripts/configure_fail2ban.sh" || log_warn "Fail2ban configuration step reported a problem."

bash "$SCRIPT_DIR/scripts/install_cli.sh" "$SSHWS_ROOT" "$VENV_PY"

log_step "Installation summary"
bash "$SCRIPT_DIR/scripts/print_summary.sh" "$SSHWS_ROOT" "$VENV_PY"

log_ok "Install complete. Run 'ssh-ws' any time to manage this install."
