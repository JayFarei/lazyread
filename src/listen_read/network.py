from __future__ import annotations

import json
import subprocess
from typing import Callable

from .config import Settings


Runner = Callable[..., subprocess.CompletedProcess[str]]


def expose_tailscale(
    settings: Settings,
    *,
    https_port: int,
    runner: Runner = subprocess.run,
) -> dict:
    """Add one tailnet-only Serve listener without resetting unrelated routes."""

    if not 1 <= https_port <= 65535:
        raise ValueError("Tailscale HTTPS port must be between 1 and 65535")
    status = runner(
        ["tailscale", "serve", "status", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if status.returncode:
        raise OSError(status.stderr.strip() or "Tailscale is unavailable")
    configuration = json.loads(status.stdout or "{}")
    expected_proxy = f"http://127.0.0.1:{settings.port}"
    matching = [
        handler.get("Proxy")
        for address, web in configuration.get("Web", {}).items()
        if address.endswith(f":{https_port}")
        for handler in web.get("Handlers", {}).values()
    ]
    if matching and expected_proxy not in matching:
        raise ValueError(
            f"Tailscale HTTPS port {https_port} already serves another local application"
        )
    if not matching:
        served = runner(
            [
                "tailscale",
                "serve",
                "--bg",
                "--yes",
                f"--https={https_port}",
                str(settings.port),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if served.returncode:
            raise OSError(served.stderr.strip() or "Tailscale Serve failed")

    identity = runner(
        ["tailscale", "status", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if identity.returncode:
        raise OSError(identity.stderr.strip() or "Tailscale identity is unavailable")
    dns_name = json.loads(identity.stdout).get("Self", {}).get("DNSName", "").rstrip(".")
    url = f"https://{dns_name}:{https_port}" if dns_name else None
    return {"status": "already_exposed" if matching else "exposed", "url": url, "https_port": https_port}
