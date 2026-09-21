"""Recent-log retrieval with sanitization.

Every source is read through a fixed, allowlisted journalctl unit name or
a fixed file path -- never a caller-supplied path -- and every line is run
through a redaction filter before it leaves this module.
"""
from __future__ import annotations

import re
import subprocess

JOURNAL_SOURCES = {
    "ssh": "ssh.service",
    "bridge": "sshws-bridge.service",
    "nginx": "nginx.service",
    "manager": "sshws-manager.service",
}

FILE_SOURCES = {
    "certbot": "/var/log/letsencrypt/letsencrypt.log",
    "install": "/var/log/ssh-websocket-server/install.log",
}

REDACTIONS = [
    (re.compile(r"(password[=:\s]+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(passwd[=:\s]+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(secret[=:\s]+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(token[=:\s]+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(session[_-]?id[=:\s]+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
     "[REDACTED PRIVATE KEY]"),
    (re.compile(r"Cookie:\s*\S+", re.IGNORECASE), "Cookie: [REDACTED]"),
]


def sanitize(line: str) -> str:
    for pattern, repl in REDACTIONS:
        line = pattern.sub(repl, line)
    return line


def tail_journal(source: str, lines: int = 200) -> list[str]:
    unit = JOURNAL_SOURCES.get(source)
    if unit is None:
        raise ValueError(f"unknown log source: {source}")
    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=10, check=False, shell=False,
        )
    except FileNotFoundError:
        return ["journalctl is not available on this system"]
    return [sanitize(line) for line in result.stdout.splitlines()]


def tail_file(source: str, lines: int = 200) -> list[str]:
    path = FILE_SOURCES.get(source)
    if path is None:
        raise ValueError(f"unknown log source: {source}")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.readlines()
    except FileNotFoundError:
        return [f"no log file yet at {path}"]
    except PermissionError:
        return [f"permission denied reading {path}"]
    return [sanitize(line.rstrip("\n")) for line in content[-lines:]]


def tail(source: str, lines: int = 200) -> list[str]:
    if source in JOURNAL_SOURCES:
        return tail_journal(source, lines)
    if source in FILE_SOURCES:
        return tail_file(source, lines)
    raise ValueError(f"unknown log source: {source}")


def available_sources() -> list[str]:
    return sorted(set(JOURNAL_SOURCES) | set(FILE_SOURCES))
