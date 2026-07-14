from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _free_bytes(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free


def _physical_memory_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError):
        return None


def _version(command: str, *arguments: str) -> tuple[str | None, tuple[int, ...]]:
    path = shutil.which(command)
    if path is None:
        return None, ()
    try:
        result = subprocess.run(
            [path, *arguments], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, ()
    value = (result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr) else ""
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    parsed = tuple(int(part) for part in match.groups(default="0")) if match else ()
    return value or None, parsed


def report(home: Path) -> dict[str, Any]:
    system = platform.system()
    machine = platform.machine()
    node_version, node_parts = _version("node", "--version")
    ffmpeg_version, ffmpeg_parts = _version("ffmpeg", "-version")
    uv_version, uv_parts = _version("uv", "--version")
    macos_parts = tuple(
        int(part) for part in (platform.mac_ver()[0] or "0").split(".")[:2]
    )
    checks = {
        "python": {
            "available": sys.version_info >= (3, 11),
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "node": {
            "available": bool(node_parts and node_parts >= (20, 19, 0)),
            "version": node_version,
            "path": shutil.which("node"),
            "minimum": "20.19.0",
            "install_hint": "brew install node",
        },
        "defuddle": {
            "available": shutil.which("defuddle") is not None,
            "path": shutil.which("defuddle"),
            "managed_install_required": shutil.which("defuddle") is None,
        },
        "ffmpeg": {
            "available": bool(ffmpeg_parts and ffmpeg_parts >= (6, 0, 0)),
            "version": ffmpeg_version,
            "path": shutil.which("ffmpeg"),
            "minimum": "6.0.0",
            "install_hint": "brew install ffmpeg",
        },
        "uv": {
            "available": bool(uv_parts and uv_parts >= (0, 5, 0)),
            "version": uv_version,
            "path": shutil.which("uv"),
            "minimum": "0.5.0",
            "install_hint": "brew install uv",
        },
        "tailscale": {"available": shutil.which("tailscale") is not None, "path": shutil.which("tailscale")},
        "disk": {"free_bytes": _free_bytes(home), "recommended_bytes": 12 * 1024**3},
        "memory": {"physical_bytes": _physical_memory_bytes(), "recommended_bytes": 16 * 1024**3},
    }
    memory = checks["memory"]["physical_bytes"]
    requirements = {
        "platform": system == "Darwin" and machine == "arm64" and macos_parts >= (14, 0),
        "python": bool(checks["python"]["available"]),
        "node": bool(checks["node"]["available"]),
        "ffmpeg": bool(checks["ffmpeg"]["available"]),
        "uv": bool(checks["uv"]["available"]),
        "disk": int(checks["disk"]["free_bytes"]) >= int(checks["disk"]["recommended_bytes"]),
        "memory": memory is not None and int(memory) >= int(checks["memory"]["recommended_bytes"]),
    }
    blockers = [name for name, available in requirements.items() if not available]
    supported = not blockers
    return {
        "supported": supported,
        "platform": {"system": system, "machine": machine, "release": platform.release()},
        "home": str(home),
        "checks": checks,
        "requirements": requirements,
        "blockers": blockers,
        "downloads_started": False,
        "process_id": os.getpid(),
    }
