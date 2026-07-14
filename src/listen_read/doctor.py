from __future__ import annotations

import os
import platform
import shutil
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


def report(home: Path) -> dict[str, Any]:
    system = platform.system()
    machine = platform.machine()
    checks = {
        "python": {
            "available": sys.version_info >= (3, 11),
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "node": {"available": shutil.which("node") is not None, "path": shutil.which("node")},
        "defuddle": {
            "available": shutil.which("defuddle") is not None,
            "path": shutil.which("defuddle"),
            "managed_install_required": shutil.which("defuddle") is None,
        },
        "ffmpeg": {"available": shutil.which("ffmpeg") is not None, "path": shutil.which("ffmpeg")},
        "uv": {"available": shutil.which("uv") is not None, "path": shutil.which("uv")},
        "tailscale": {"available": shutil.which("tailscale") is not None, "path": shutil.which("tailscale")},
        "disk": {"free_bytes": _free_bytes(home), "recommended_bytes": 12 * 1024**3},
        "memory": {"physical_bytes": _physical_memory_bytes(), "recommended_bytes": 16 * 1024**3},
    }
    supported = system == "Darwin" and machine == "arm64"
    return {
        "supported": supported,
        "platform": {"system": system, "machine": machine, "release": platform.release()},
        "home": str(home),
        "checks": checks,
        "downloads_started": False,
        "process_id": os.getpid(),
    }
