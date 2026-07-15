from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _environment(primary: str, legacy: str, default: str | None = None) -> str | None:
    return os.environ.get(primary) or os.environ.get(legacy) or default


def _default_home_named(name: str) -> Path:
    return Path.home() / "Library" / "Application Support" / name


def _legacy_server_is_running(home: Path) -> bool:
    pid_file = home / "runtime" / "server.pid"
    try:
        pid = int(pid_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return False
    except PermissionError:
        return True
    return True


def _require_stopped_legacy_server(home: Path) -> None:
    if _legacy_server_is_running(home):
        raise OSError(
            "The legacy Listen Read server is still running. Stop the PID in "
            f"{home / 'runtime' / 'server.pid'} before starting Lazyreader."
        )


def default_home() -> Path:
    configured = _environment("LAZYREADER_HOME", "LISTEN_READ_HOME")
    if configured:
        return Path(configured).expanduser()
    return _default_home_named("Lazyreader")


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
        web = _environment("LAZYREADER_WEB_DIR", "LISTEN_READ_WEB_DIR")
        return cls(
            home=Path(home).expanduser() if home else default_home(),
            host=host
            or _environment("LAZYREADER_HOST", "LISTEN_READ_HOST", "127.0.0.1")
            or "127.0.0.1",
            port=port
            or int(
                _environment("LAZYREADER_PORT", "LISTEN_READ_PORT", "4242") or "4242"
            ),
            web_dir=Path(web).expanduser() if web else None,
        )

    def ensure_directories(self) -> None:
        new_default = _default_home_named("Lazyreader")
        legacy_default = _default_home_named("Listen Read")
        if (
            self.home == new_default
            and not self.home.exists()
            and legacy_default.is_dir()
        ):
            _require_stopped_legacy_server(legacy_default)
            legacy_default.rename(self.home)
        self.home.mkdir(parents=True, exist_ok=True)
        legacy_database_present = any(
            (self.home / f"listen-read.sqlite{suffix}").is_file()
            for suffix in ("", "-wal", "-shm")
        )
        if legacy_database_present:
            _require_stopped_legacy_server(self.home)
        for suffix in ("", "-wal", "-shm"):
            legacy_database = self.home / f"listen-read.sqlite{suffix}"
            database = self.home / f"lazyreader.sqlite{suffix}"
            if legacy_database.is_file() and not database.exists():
                legacy_database.rename(database)
        for name in (
            "articles",
            "cache/models",
            "cache/chunks",
            "runtime",
            "logs",
            "trash",
        ):
            (self.home / name).mkdir(parents=True, exist_ok=True)
