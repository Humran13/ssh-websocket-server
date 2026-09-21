"""Read-only system/dashboard data. Everything here is either a direct
syscall/stdlib read or a call into the (allowlisted, read-only) privileged
actions -- nothing here can change system state.
"""
from __future__ import annotations

import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

from . import privileged


def hostname() -> str:
    return socket.gethostname()


def kernel() -> str:
    return platform.release()


def os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    path = Path("/etc/os-release")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                data[k] = v.strip('"')
    return data


def uptime_seconds() -> float | None:
    try:
        with open("/proc/uptime", encoding="utf-8") as fh:
            return float(fh.read().split()[0])
    except (FileNotFoundError, ValueError, IndexError):
        return None


def cpu_percent(sample_seconds: float = 0.2) -> float | None:
    def _read():
        with open("/proc/stat", encoding="utf-8") as fh:
            parts = fh.readline().split()[1:]
        nums = [int(x) for x in parts]
        idle = nums[3] + nums[4]
        total = sum(nums)
        return idle, total

    try:
        idle1, total1 = _read()
        time.sleep(sample_seconds)
        idle2, total2 = _read()
    except (FileNotFoundError, IndexError, ValueError):
        return None
    dt = total2 - total1
    if dt <= 0:
        return None
    return round((1 - (idle2 - idle1) / dt) * 100, 1)


def memory_usage() -> dict[str, int] | None:
    try:
        info = {}
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                value_kb = int(rest.strip().split()[0])
                info[key] = value_kb * 1024
    except (FileNotFoundError, ValueError, IndexError):
        return None
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    return {"total": total, "used": max(total - available, 0), "available": available}


def disk_usage(path: str = "/") -> dict[str, int]:
    usage = shutil.disk_usage(path)
    return {"total": usage.total, "used": usage.used, "free": usage.free}


def public_ip() -> str | None:
    """Best-effort local detection only -- never calls an external service.

    Opens a UDP socket to a public address (no packets are actually sent
    for a connect() on UDP) purely to ask the kernel which local interface
    / source address would be used, which is the outbound-facing IP in the
    common case of a single public interface.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("198.51.100.1", 80))  # TEST-NET-2, no traffic sent
            return s.getsockname()[0]
    except OSError:
        return None


def service_status(name: str) -> str:
    try:
        return privileged.call("service_status", {"name": name}).get("status", "unknown")
    except privileged.PrivilegedActionError:
        return "unknown"


def firewall_status() -> str:
    try:
        out = privileged.call("ufw_status", {}).get("output", "")
    except privileged.PrivilegedActionError:
        return "unknown"
    if "Status: active" in out:
        return "active"
    if "Status: inactive" in out:
        return "inactive"
    return "unknown"


def ssl_expiry(cert_path: str) -> str | None:
    p = Path(cert_path)
    if not p.exists():
        return None
    try:
        result = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", str(p)],
            capture_output=True, text=True, check=True, timeout=10, shell=False,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    line = result.stdout.strip()
    return line.split("=", 1)[1] if "=" in line else line
