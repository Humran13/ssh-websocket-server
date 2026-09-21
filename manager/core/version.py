"""Semantic version parsing/comparison used by the update flow and the
dashboard's "installed version" display."""
from __future__ import annotations

import re
from pathlib import Path

from . import paths

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def parse(v: str) -> tuple[int, int, int]:
    m = _SEMVER_RE.match(v.strip().lstrip("v"))
    if not m:
        raise ValueError(f"not a semantic version: {v!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def compare(a: str, b: str) -> int:
    pa, pb = parse(a), parse(b)
    return (pa > pb) - (pa < pb)


def installed_version() -> str:
    version_file = paths.INSTALL_ROOT / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    here = Path(__file__).resolve().parents[2] / "VERSION"
    if here.exists():
        return here.read_text(encoding="utf-8").strip()
    return "0.0.0"
