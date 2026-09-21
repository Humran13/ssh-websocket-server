#!/usr/bin/env bash
# Installs the /usr/local/bin/ssh-ws wrapper. Usage: install_cli.sh <root> <venv-python>
set -euo pipefail
SSHWS_ROOT="${1:?install root required}"
VENV_PY="${2:?venv python path required}"

cat > /usr/local/bin/ssh-ws <<EOF
#!/usr/bin/env bash
# Installed by ssh-websocket-server's install.sh. Runs the interactive
# manager as root (via sudo) since SSH-user and system-service management
# requires it -- exactly like any other Linux admin CLI tool.
set -e
exec sudo -E "$VENV_PY" "$SSHWS_ROOT/cli/ssh_ws_cli.py" "\$@"
EOF
chmod 755 /usr/local/bin/ssh-ws
echo "Installed CLI: /usr/local/bin/ssh-ws"
