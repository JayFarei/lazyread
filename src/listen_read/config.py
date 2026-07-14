from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def default_home() -> Path:
    configured = os.environ.get("LISTEN_READ_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Library" / "Application Support" / "Listen Read"


@dataclass(frozen=True, slots=True)
class Settings:
    home: Path
    host: str = "127.0.0.1"
    port: int = 4242
    web_dir: Path | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        home: str | Path | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> "Settings":
        web = os.environ.get("LISTEN_READ_WEB_DIR")
        return cls(
            home=Path(home).expanduser() if home else default_home(),
            host=host or os.environ.get("LISTEN_READ_HOST", "127.0.0.1"),
            port=port or int(os.environ.get("LISTEN_READ_PORT", "4242")),
            web_dir=Path(web).expanduser() if web else None,
        )

    def ensure_directories(self) -> None:
        for name in ("articles", "cache/models", "cache/chunks", "runtime", "logs", "trash"):
            (self.home / name).mkdir(parents=True, exist_ok=True)

