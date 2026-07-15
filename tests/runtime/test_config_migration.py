from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from lazyread.config import Settings


@pytest.mark.parametrize(
    ("legacy_home_name", "legacy_database_name"),
    (("Lazyreader", "lazyreader.sqlite"), ("Listen Read", "listen-read.sqlite")),
)
def test_default_home_moves_a_legacy_library_and_database(
    tmp_path: Path,
    monkeypatch,
    legacy_home_name: str,
    legacy_database_name: str,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LAZYREAD_HOME", raising=False)
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.delenv("LISTEN_READ_HOME", raising=False)
    legacy = tmp_path / "Library" / "Application Support" / legacy_home_name
    legacy.mkdir(parents=True)
    (legacy / legacy_database_name).write_bytes(b"existing library")
    (legacy / f"{legacy_database_name}-wal").write_bytes(b"pending transaction")
    (legacy / f"{legacy_database_name}-shm").write_bytes(b"shared memory")
    (legacy / "articles").mkdir()

    settings = Settings.from_environment()
    settings.ensure_directories()

    expected = tmp_path / "Library" / "Application Support" / "Lazyread"
    assert settings.home == expected
    assert not legacy.exists()
    assert (expected / "lazyread.sqlite").read_bytes() == b"existing library"
    assert (expected / "lazyread.sqlite-wal").read_bytes() == b"pending transaction"
    assert (expected / "lazyread.sqlite-shm").read_bytes() == b"shared memory"


def test_default_home_adopts_legacy_library_when_new_home_is_empty(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LAZYREAD_HOME", raising=False)
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.delenv("LISTEN_READ_HOME", raising=False)
    application_support = tmp_path / "Library" / "Application Support"
    new_home = application_support / "Lazyread"
    new_home.mkdir(parents=True)
    legacy = application_support / "Lazyreader"
    legacy.mkdir()
    (legacy / "lazyreader.sqlite").write_bytes(b"catalog")

    Settings.from_environment().ensure_directories()

    assert (new_home / "lazyread.sqlite").read_bytes() == b"catalog"
    assert not legacy.exists()


def test_default_home_refuses_to_merge_new_and_legacy_data(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LAZYREAD_HOME", raising=False)
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.delenv("LISTEN_READ_HOME", raising=False)
    application_support = tmp_path / "Library" / "Application Support"
    new_home = application_support / "Lazyread"
    new_home.mkdir(parents=True)
    (new_home / "marker").write_text("new", encoding="utf-8")
    legacy = application_support / "Lazyreader"
    legacy.mkdir()
    (legacy / "lazyreader.sqlite").write_bytes(b"catalog")

    with pytest.raises(OSError, match="will not merge"):
        Settings.from_environment().ensure_directories()

    assert (new_home / "marker").read_text(encoding="utf-8") == "new"
    assert (legacy / "lazyreader.sqlite").read_bytes() == b"catalog"


@pytest.mark.parametrize("legacy_name", ("LAZYREADER_HOME", "LISTEN_READ_HOME"))
def test_legacy_home_environment_variables_remain_supported_aliases(
    tmp_path: Path, monkeypatch, legacy_name: str
) -> None:
    legacy_configured = tmp_path / "custom-library"
    monkeypatch.delenv("LAZYREAD_HOME", raising=False)
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.delenv("LISTEN_READ_HOME", raising=False)
    monkeypatch.setenv(legacy_name, str(legacy_configured))

    assert Settings.from_environment().home == legacy_configured


def test_new_environment_variable_takes_precedence_over_legacy_alias(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LAZYREAD_HOME", str(tmp_path / "new"))
    monkeypatch.setenv("LAZYREADER_HOME", str(tmp_path / "lazyreader"))
    monkeypatch.setenv("LISTEN_READ_HOME", str(tmp_path / "listen-read"))

    assert Settings.from_environment().home == tmp_path / "new"


def test_migration_refuses_to_move_an_active_legacy_library(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LAZYREAD_HOME", raising=False)
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.delenv("LISTEN_READ_HOME", raising=False)
    legacy = tmp_path / "Library" / "Application Support" / "Lazyreader"
    pid_file = legacy / "runtime" / "server.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    settings = Settings.from_environment()

    with pytest.raises(OSError, match="legacy Lazyreader server is still running"):
        settings.ensure_directories()
    assert legacy.is_dir()
    assert not settings.home.exists()


@pytest.mark.parametrize("legacy_name", ("lazyreader.sqlite", "listen-read.sqlite"))
def test_crash_resident_wal_rows_survive_database_rename(
    tmp_path: Path, legacy_name: str
) -> None:
    home = tmp_path / "library"
    home.mkdir()
    legacy_database = home / legacy_name
    program = """
import os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('PRAGMA journal_mode=WAL')
connection.execute('PRAGMA wal_autocheckpoint=0')
connection.execute('CREATE TABLE migration_proof (value TEXT)')
connection.execute("INSERT INTO migration_proof VALUES ('survived')")
connection.commit()
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", program, str(legacy_database)], check=True)
    assert (home / f"{legacy_name}-wal").stat().st_size > 0

    Settings(home=home).ensure_directories()

    with sqlite3.connect(home / "lazyread.sqlite") as connection:
        assert connection.execute("SELECT value FROM migration_proof").fetchone() == (
            "survived",
        )


def test_refuses_to_mix_new_and_legacy_database_families(tmp_path: Path) -> None:
    home = tmp_path / "library"
    home.mkdir()
    (home / "lazyread.sqlite").write_bytes(b"new")
    (home / "lazyreader.sqlite").write_bytes(b"old")
    (home / "lazyreader.sqlite-wal").write_bytes(b"old-wal")

    with pytest.raises(OSError, match="Multiple database families"):
        Settings(home=home).ensure_directories()

    assert (home / "lazyread.sqlite").read_bytes() == b"new"
    assert (home / "lazyreader.sqlite-wal").read_bytes() == b"old-wal"


def test_refuses_an_incomplete_database_family(tmp_path: Path) -> None:
    home = tmp_path / "library"
    home.mkdir()
    (home / "lazyreader.sqlite-wal").write_bytes(b"orphan")

    with pytest.raises(OSError, match="is incomplete"):
        Settings(home=home).ensure_directories()

    assert not (home / "lazyread.sqlite-wal").exists()
