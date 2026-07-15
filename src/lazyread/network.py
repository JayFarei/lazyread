from __future__ import annotations

import json
import subprocess
from typing import Callable
import urllib.request

from .config import Settings


Runner = Callable[..., subprocess.CompletedProcess[str]]
HealthCheck = Callable[[Settings], bool]


def _lazyread_is_healthy(settings: Settings) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{settings.port}/api/health", timeout=1
        ) as response:
            payload = json.loads(response.read())
        return (
            response.status == 200
            and payload.get("status") == "ok"
            and bool(payload.get("version"))
        )
    except (OSError, json.JSONDecodeError):
        return False


def expose_tailscale(
    settings: Settings,
    *,
    https_port: int,
    runner: Runner = subprocess.run,
    health_check: HealthCheck = _lazyread_is_healthy,
) -> dict:
    """Add one tailnet-only Serve listener without resetting unrelated routes."""

    if not 1 <= https_port <= 65535:
        raise ValueError("Tailscale HTTPS port must be between 1 and 65535")
    if not health_check(settings):
        raise ValueError(
            f"Lazyread is not healthy on local port {settings.port}; refusing to expose it"
        )
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
    tcp_owner = configuration.get("TCP", {}).get(str(https_port))
    if tcp_owner and not matching:
        raise ValueError(
            f"Tailscale TCP port {https_port} is already owned by another listener"
        )
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
    dns_name = (
        json.loads(identity.stdout).get("Self", {}).get("DNSName", "").rstrip(".")
    )
    url = f"https://{dns_name}:{https_port}" if dns_name else None
    return {
        "status": "already_exposed" if matching else "exposed",
        "url": url,
        "https_port": https_port,
    }
