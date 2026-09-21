# Connecting: what the WebSocket endpoint actually is

This project exposes SSH over a WebSocket transport in addition to plain
SSH. It is important to understand what that means before connecting.

## The three endpoints

| Mode | Example | Notes |
|---|---|---|
| Direct SSH | `ssh -p 22 user@server.example.com` | Ordinary OpenSSH. Any SSH client works. Nothing about this project changes it. |
| Plain WebSocket | `ws://server.example.com/ssh` | An HTTP(S) connection that upgrades to the WebSocket protocol, which then carries a raw SSH byte stream to the local sshd. |
| Secure WebSocket | `wss://server.example.com/ssh` | Same as above, over TLS. |

**The `ws://`/`wss://` URLs above are this server's WebSocket endpoint --
they are not a connection string any standard OpenSSH client understands
directly.** A normal `ssh` client speaks the SSH protocol straight to a
TCP port; it does not speak HTTP/WebSocket framing. To use the WebSocket
endpoints you need either:

1. **A WebSocket-capable SSH client / tunnel tool** that understands how
   to wrap SSH traffic inside a WebSocket connection to the given host,
   port and path, and then hands the resulting decoded stream to a normal
   SSH session -- these exist as both standalone tools and features built
   into some mobile SSH apps. Configure it with:
   - **Host / address**: the domain or IP shown by `ssh-ws` / the panel
   - **Port**: the WS or WSS port (80/443 by default, or whatever you
     configured)
   - **Path**: the WebSocket path (default `/ssh`)
   - **TLS / SNI**: for `wss://`, use the domain name (not the bare IP)
     as the SNI/hostname so certificate validation succeeds
   - Once connected, it presents a normal SSH session backed by your
     usual username/password (or key, if you've configured OpenSSH for
     key auth on this server -- this project does not change that).

2. **A local WebSocket-to-TCP tunnel** (the same idea `websockify` itself
   implements, just running on your own machine instead of the server) that
   opens `ws://`/`wss://server/path` and exposes it as a plain local TCP
   port, which you then point a completely ordinary SSH client at
   (`ssh -p <local-port> user@127.0.0.1`).

Either way, the WebSocket layer is a **transport wrapper** around the same
authenticated SSH session your direct-SSH users get -- it does not weaken
or change SSH's own authentication. A locked, disabled, or expired managed
account is just as locked out over WebSocket as over direct SSH, because
both paths terminate at the exact same local `sshd`.

## Why use WebSocket at all?

The WebSocket transport is useful specifically where a network only
allows outbound HTTP/HTTPS traffic (looks like ordinary web browsing) but
blocks raw port 22, or where a captive proxy only forwards
HTTP(S)-shaped connections. It is not a security feature by itself --
`wss://` on port 443 gets you TLS, but the SSH protocol underneath is
already encrypted and authenticated on its own.

## Troubleshooting

- **"Connection refused" on the WS/WSS port** -- check `ssh-ws` ->
  Dashboard / Health Checks. The most common cause is the firewall not
  allowing that port yet (`ssh-ws` -> Firewall Status -> sync rules) or
  Nginx not running (`systemctl status nginx`).
- **WS works but WSS doesn't** -- WSS requires a certificate. Check
  `ssh-ws` -> Domain / SSL. A certificate cannot be issued for a bare IP
  address; you need a domain that resolves to this server.
- **"101 Switching Protocols" not returned** -- this is exactly what the
  built-in health check (`ssh-ws` -> Health Checks, or the panel's Health
  page) verifies for you: it sends a real WebSocket handshake request and
  confirms the bridge answers it, rather than just checking the port is
  open.
- **Client connects but SSH login fails** -- this is a normal SSH
  authentication failure once you're through the WebSocket layer; check
  the account's status (enabled/expired/session limit) from the Users
  page, and check `ssh-ws` -> View Logs -> `ssh`.
- **Domain resolves to the wrong thing after adding it** -- DNS
  propagation can take time; the Domain/SSL page's DNS check is
  informational only and will not block you from retrying certificate
  issuance once it catches up.
