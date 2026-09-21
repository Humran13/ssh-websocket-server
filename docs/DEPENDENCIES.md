# Dependency and license audit

## This project's own Python dependencies (`manager/requirements.txt`)

| Package | License | Notes |
|---|---|---|
| Flask | BSD-3-Clause | Web framework |
| Werkzeug | BSD-3-Clause | Flask's WSGI toolkit; also provides `generate_password_hash`/`check_password_hash` (PBKDF2) used for admin auth |
| Flask-WTF | BSD-3-Clause | CSRF protection |
| WTForms | BSD-3-Clause | Flask-WTF dependency |
| Flask-Limiter | MIT | Login rate limiting |
| gunicorn | MIT | WSGI server the manager runs under |

All permissive, all compatible with this project's own MIT license with
no copyleft obligations.

## The WebSocket bridge: websockify

**License: LGPLv3.** This is the one non-permissive dependency, and it's
used deliberately rather than avoided:

- It is installed as an ordinary, unmodified PyPI package
  (`websockify==0.11.0`, pinned) into this project's own venv, and run as
  its own OS process (`python -m websockify ...`, see
  `systemd/sshws-bridge.service`) -- this project's code never `import`s
  it or links against it.
- Because it's used at arm's length as a separate program rather than a
  linked library, and the exact package installed is swappable by the
  administrator (any other LGPLv3-compliant build of websockify, or even
  a different WS↔TCP bridge with the same command-line contract, could be
  substituted by editing one systemd unit), LGPLv3's terms are satisfied
  without imposing any copyleft obligation on this project's own MIT code.
- Its own transitive dependencies as of 0.11.0 (from `pip show
  websockify`): `numpy`, `redis`, `requests`, `simplejson`, `jwcrypto` --
  all themselves permissively licensed (BSD/Apache-2.0/MIT). `numpy` in
  particular is the reason the venv setup step in `install.sh` can take a
  few minutes on first run (and longer still on Ubuntu 18.04's older
  Python, where a compatible wheel may not exist and it must build from
  source -- which is why `build-essential`/`python3-dev` are always
  installed as part of the dependency list, not only when needed).

## System packages (installed from Ubuntu's own archives, not bundled)

OpenSSH, Nginx, SQLite, UFW, Fail2ban, Certbot + python3-certbot-nginx,
jq, git, curl. None of these are vendored or modified by this project;
`install.sh` installs them via `apt-get` from the distribution's own
signed package archives, and their licenses (a mix of BSD-style, GPLv2,
and GPLv3 depending on the package) apply to those packages independently
of this project's own MIT license -- this project does not statically
link against any of them.

## What this project does *not* do

- No arbitrary/unverified binary downloads: every external dependency
  above comes from either PyPI (via pinned `pip install`) or Ubuntu's own
  apt archives (signed, standard `apt-get install`) -- never a bare
  `curl | bash` of a third-party script, and never an unpinned "latest"
  install for anything security-relevant.
- No bundling of GPL/LGPL source into this project's own MIT-licensed
  files.
