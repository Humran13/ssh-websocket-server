# nginx/

This directory holds reference Nginx configuration only. The config that
actually runs on an installed server is generated dynamically by
`manager/core/network.py` (`render_nginx_config`) from
`/etc/ssh-websocket-server/config.json`, written to
`/etc/nginx/sites-available/ssh-websocket-server.conf`, and symlinked into
`sites-enabled/` -- it is never hand-edited on disk, so there is nothing to
keep in sync here beyond documentation.

See `docs/CLIENTS.md` for what the generated config actually does
(WebSocket upgrade headers, proxying to the local bridge, TLS termination
for `wss://`), and `manager/core/network.py` for the exact Jinja-free
string templates used to generate it.
