from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


LEGACY_INSTALLATIONS = (
    ("Lazyreader", "Lazyreader", "lazyreader.sqlite"),
    ("Listen Read", "Listen Read", "listen-read.sqlite"),
)
DATABASE_SUFFIXES = ("", "-wal", "-shm")


def _environment(*names: str, default: str | None = None) -> str | None:
    return next((value for name in names if (value := os.environ.get(name))), default)


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


def _require_stopped_legacy_server(home: Path, product_name: str) -> None:
    if _legacy_server_is_running(home):
        raise OSError(
            f"The legacy {product_name} server is still running. Stop the PID in "
            f"{home / 'runtime' / 'server.pid'} before starting Lazyread."
        )


def _database_family_present(home: Path, basename: str) -> bool:
    return any((home / f"{basename}{suffix}").is_file() for suffix in DATABASE_SUFFIXES)


def _migrate_database_family(home: Path) -> None:
    families = (("Lazyread", "lazyread.sqlite"),) + tuple(
        (product_name, basename)
        for product_name, _, basename in LEGACY_INSTALLATIONS
    )
    present = [family for family in families if _database_family_present(home, family[1])]
    if not present:
        return
    if len(present) > 1:
        names = ", ".join(name for name, _ in present)
        raise OSError(
            f"Multiple database families are present in {home}: {names}. "
            "Lazyread will not combine them; move the unexpected family aside and retry."
        )
    product_name, basename = present[0]
    if not (home / basename).is_file():
        raise OSError(
            f"The {product_name} database family in {home} is incomplete: "
            f"{basename} is missing. Restore the main database before retrying."
        )
    if basename == "lazyread.sqlite":
        return
    _require_stopped_legacy_server(home, product_name)
    for suffix in DATABASE_SUFFIXES:
        legacy_database = home / f"{basename}{suffix}"
        if legacy_database.is_file():
            legacy_database.rename(home / f"lazyread.sqlite{suffix}")


def default_home() -> Path:
    configured = _environment("LAZYREAD_HOME", "LAZYREADER_HOME", "LISTEN_READ_HOME")
    if configured:
        return Path(configured).expanduser()
    return _default_home_named("Lazyread")


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
        web = _environment("LAZYREAD_WEB_DIR", "LAZYREADER_WEB_DIR", "LISTEN_READ_WEB_DIR")
        return cls(
            home=Path(home).expanduser() if home else default_home(),
            host=host
            or _environment(
                "LAZYREAD_HOST",
                "LAZYREADER_HOST",
                "LISTEN_READ_HOST",
                default="127.0.0.1",
            )
            or "127.0.0.1",
            port=port
            or int(
                _environment(
                    "LAZYREAD_PORT",
                    "LAZYREADER_PORT",
                    "LISTEN_READ_PORT",
                    default="4242",
                )
                or "4242"
            ),
            web_dir=Path(web).expanduser() if web else None,
        )

    def ensure_directories(self) -> None:
        new_default = _default_home_named("Lazyread")
        if self.home == new_default:
            legacy_homes = [
                (product_name, legacy_home)
                for product_name, home_name, _ in LEGACY_INSTALLATIONS
                if (legacy_home := _default_home_named(home_name)).is_dir()
                and any(legacy_home.iterdir())
            ]
            if len(legacy_homes) > 1:
                names = ", ".join(name for name, _ in legacy_homes)
                raise OSError(
                    f"Multiple legacy Lazyread homes are present: {names}. "
                    "Move the inactive home aside before retrying."
                )
            if legacy_homes:
                product_name, legacy_home = legacy_homes[0]
                if self.home.exists() and any(self.home.iterdir()):
                    raise OSError(
                        f"Both {self.home} and the legacy {product_name} home "
                        f"{legacy_home} contain data. Lazyread will not merge them; "
                        "move the inactive home aside before retrying."
                    )
                _require_stopped_legacy_server(legacy_home, product_name)
                if self.home.exists():
                    self.home.rmdir()
                legacy_home.rename(self.home)
        self.home.mkdir(parents=True, exist_ok=True)
        _migrate_database_family(self.home)
        for name in (
            "articles",
            "cache/models",
            "cache/chunks",
            "runtime",
            "logs",
            "trash",
        ):
            (self.home / name).mkdir(parents=True, exist_ok=True)
