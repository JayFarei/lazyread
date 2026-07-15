from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from lazyreader.config import Settings


def test_default_home_moves_the_legacy_library_and_database(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.delenv("LISTEN_READ_HOME", raising=False)
    legacy = tmp_path / "Library" / "Application Support" / "Listen Read"
    legacy.mkdir(parents=True)
    (legacy / "listen-read.sqlite").write_bytes(b"existing library")
    (legacy / "listen-read.sqlite-wal").write_bytes(b"pending transaction")
    (legacy / "listen-read.sqlite-shm").write_bytes(b"shared memory")
    (legacy / "articles").mkdir()

    settings = Settings.from_environment()
    settings.ensure_directories()

    expected = tmp_path / "Library" / "Application Support" / "Lazyreader"
    assert settings.home == expected
    assert not legacy.exists()
    assert (expected / "lazyreader.sqlite").read_bytes() == b"existing library"
    assert (expected / "lazyreader.sqlite-wal").read_bytes() == b"pending transaction"
    assert (expected / "lazyreader.sqlite-shm").read_bytes() == b"shared memory"


def test_legacy_home_environment_variable_remains_a_supported_alias(
    tmp_path: Path, monkeypatch
) -> None:
    legacy_configured = tmp_path / "custom-library"
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.setenv("LISTEN_READ_HOME", str(legacy_configured))

    assert Settings.from_environment().home == legacy_configured


def test_new_environment_variable_takes_precedence_over_legacy_alias(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("LAZYREADER_HOME", str(tmp_path / "new"))
    monkeypatch.setenv("LISTEN_READ_HOME", str(tmp_path / "legacy"))

    assert Settings.from_environment().home == tmp_path / "new"


def test_migration_refuses_to_move_an_active_legacy_library(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LAZYREADER_HOME", raising=False)
    monkeypatch.delenv("LISTEN_READ_HOME", raising=False)
    legacy = tmp_path / "Library" / "Application Support" / "Listen Read"
    pid_file = legacy / "runtime" / "server.pid"
    pid_file.parent.mkdir(parents=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    settings = Settings.from_environment()

    with pytest.raises(OSError, match="legacy Listen Read server is still running"):
        settings.ensure_directories()
    assert legacy.is_dir()
    assert not settings.home.exists()


def test_crash_resident_wal_rows_survive_database_rename(tmp_path: Path) -> None:
    home = tmp_path / "library"
    home.mkdir()
    legacy_database = home / "listen-read.sqlite"
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
    assert (home / "listen-read.sqlite-wal").stat().st_size > 0

    Settings(home=home).ensure_directories()

    with sqlite3.connect(home / "lazyreader.sqlite") as connection:
        assert connection.execute("SELECT value FROM migration_proof").fetchone() == (
            "survived",
        )
