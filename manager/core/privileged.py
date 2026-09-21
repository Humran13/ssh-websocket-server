"""Client side of the root helper: calls scripts/priv_helper.py via sudo.

The manager (Flask app) and the CLI both run as the unprivileged `sshws`
service user. Every operation that needs root goes through this single
function, which shells out to `sudo <venv-python> priv_helper.py` and
passes the action + arguments as one JSON object over stdin -- never as
command-line arguments -- so secrets (e.g. a new password) never appear
in `ps` output. See scripts/priv_helper.py for the allowlisted actions
and scripts/sshws.sudoers for the exact sudo rule.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from . import paths


class PrivilegedActionError(RuntimeError):
    pass


def _call_in_process(action: str, args: dict) -> dict:
    """Fast path for callers that are already root (e.g. `sudo ssh-ws ...`
    run interactively by an administrator): load priv_helper.py's own
    validated action functions directly instead of a sudo round-trip.
    Every safety check in priv_helper.py still applies -- this only skips
    the extra process hop, not any validation.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("priv_helper", str(paths.PRIV_HELPER))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    handler = module.ACTIONS.get(action)
    if handler is None:
        raise PrivilegedActionError(f"unknown action: {action!r}")
    try:
        return handler(args)
    except module.HelperError as exc:
        raise PrivilegedActionError(str(exc)) from exc
    except subprocess.CalledProcessError as exc:
        raise PrivilegedActionError(f"{' '.join(exc.cmd)} failed: {exc.stderr.strip()}") from exc


def call(action: str, args: dict | None = None, timeout: int = 40) -> dict:
    args = args or {}
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return _call_in_process(action, args)

    payload = json.dumps({"action": action, "args": args})
    python_exe = sys.executable
    cmd = ["sudo", "-n", python_exe, str(paths.PRIV_HELPER)]
    try:
        result = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise PrivilegedActionError("sudo is not available on this system") from exc
    except subprocess.TimeoutExpired as exc:
        raise PrivilegedActionError(f"privileged action '{action}' timed out") from exc

    stdout = result.stdout.strip()
    if not stdout:
        raise PrivilegedActionError(
            f"privileged action '{action}' produced no output "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    try:
        parsed = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise PrivilegedActionError(f"could not parse helper output: {stdout!r}") from exc

    if not parsed.get("ok"):
        raise PrivilegedActionError(parsed.get("error", "unknown privileged helper error"))
    return parsed.get("data", {})
