"""Hardware and OS information."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from typing import Any

import psutil

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _powershell_json(command: str) -> Any:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"{command} | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW,
        ).stdout.strip()
        return json.loads(out) if out else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def gpus() -> list[dict[str, Any]]:
    if sys.platform != "win32":
        return []
    data = _powershell_json(
        "Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM,"
        "CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate")
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def gpu_vendor(gpu_list: list[dict[str, Any]]) -> str:
    names = " ".join(str(g.get("Name", "")) for g in gpu_list).lower()
    for key, vendor in (("nvidia", "nvidia"), ("geforce", "nvidia"), ("radeon", "amd"),
                        ("amd", "amd"), ("intel", "intel")):
        if key in names:
            return vendor
    return "unknown"


def collect() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    g = gpus()
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            u = shutil.disk_usage(part.mountpoint)
            disks.append({"drive": part.mountpoint, "free_gb": round(u.free / 2**30, 1),
                          "total_gb": round(u.total / 2**30, 1)})
        except OSError:
            pass
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": sys.version.split()[0],
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "ram_gb": round(vm.total / 2**30, 1),
        "gpus": g,
        "gpu_vendor": gpu_vendor(g),
        "disks": disks,
    }
