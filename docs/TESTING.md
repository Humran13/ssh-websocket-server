# Testing this project

## Unit tests (pytest)

Covers everything platform-independent in `manager/core/*.py`: config
validation, username/domain/WS-path/port validation, Nginx template
rendering, user lifecycle and its safety rules (only project-managed,
`uid >= 1000` accounts can be touched; delete requires confirmation),
password hashing, backup/restore (including a path-traversal regression
test and the same-second-filename-collision regression test), domain/WSS
state transitions with rollback-on-invalid-config, firewall
allow-before-enable ordering, and log redaction.

```bash
python -m venv .venv && . .venv/Scripts/activate   # or bin/activate on Linux/macOS
pip install -r manager/requirements.txt pytest pytest-cov ruff
pytest tests/unit -q
ruff check manager cli scripts tests
```

Every test runs against a throwaway directory (`tmp_path` fixture wired
through `SSHWS_ETC`/`SSHWS_VAR`/`SSHWS_LOG`/... env vars -- see
`tests/unit/conftest.py` and `manager/core/paths.py`), so the suite never
touches real system paths and needs no root/Linux -- it runs the same way
on the Windows machine this project was developed on as it does in CI.

Privileged actions (`core.privileged.call`) are stubbed with a fake in
these tests; the actual `scripts/priv_helper.py` allowlist/validation
logic is exercised for real inside the integration tests below, since it
imports `pwd`/`grp` and genuinely needs Linux.

## Shell script linting

```bash
shellcheck install.sh update.sh uninstall.sh lib/*.sh scripts/*.sh
```

Zero findings as of this writing (verified via the official
`koalaman/shellcheck` Docker image, since shellcheck itself doesn't ship
for Windows).

## Integration tests (Docker, full install)

```bash
bash tests/integration/run-matrix.sh              # all 5 Ubuntu versions
bash tests/integration/run-matrix.sh 22.04 24.04   # just these
```

For each requested Ubuntu version, this:

1. Builds a systemd-capable container (`tests/integration/Dockerfile` --
   the standard "systemd as PID 1 under Docker" pattern, using
   `--privileged --cgroupns=host` and the real `/sys/fs/cgroup`).
2. Copies the repo in and runs the **real** `install.sh` non-interactively
   (`--yes --skip-ssl`, a throwaway admin password), exactly as a VPS
   operator would (minus the curl-pipe bootstrap step, since the repo is
   already present).
3. Checks that `ssh`, `nginx`, and `sshws-manager` are all `active`,
   `nginx -t` passes, and a real WebSocket handshake against the `/ssh`
   endpoint on port 80 returns `101 Switching Protocols` -- not just "is
   the port open."
4. Prints a Markdown compatibility table, which is what
   `docs/COMPATIBILITY.md` is generated from.

This exercises the actual apt installs, actual systemd units, and actual
Nginx config generation/validation against each real Ubuntu release --
it is not a simulation or a hand-written "supported versions" list.

### Windows/git-bash notes

Docker Desktop's Windows CLI interop rewrites arguments that look like
Unix paths, which corrupts container-side paths like `/sys/fs/cgroup` or
volume specs containing `:`. `run-matrix.sh` sets `MSYS_NO_PATHCONV=1` and
converts host-side paths through `cygpath -w` itself to work around this;
on Linux/macOS both are no-ops.

## What is *not* covered by automated testing

- A real cloud VPS (see README "Known limitations") -- cloud-init,
  provider-specific firewalls/networking, and kernel differences aren't
  reachable from a container-based test.
- The interactive prompts in `install.sh` themselves (the integration
  tests run it with `--yes` and explicit flags); the prompt/validation
  functions they call (`lib/validate.sh`) mirror the Python-side
  validation in `manager/core/config.py`, which *is* unit tested.
- Actual Let's Encrypt certificate issuance (would require a real,
  publicly-resolvable domain and exposed port 80/443); `--skip-ssl` is
  used in the integration matrix for this reason. The certbot invocation
  itself (`scripts/priv_helper.py::action_certbot_issue`) uses the
  standard, well-established `certbot --nginx` flow.
