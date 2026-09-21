"""Services the web UI is allowed to offer a restart button for.

Deliberately narrower than priv_helper.py's own SERVICE_ALLOWLIST (which
also accepts "ssh" and "fail2ban") -- restarting sshd from the panel would
be an easy way to accidentally lock out the very session used to click
the button, so it is only ever done by the CLI/administrator directly on
the box, never a single click in the browser.
"""
MANAGED_SERVICES = {"nginx", "sshws-bridge", "sshws-manager"}
