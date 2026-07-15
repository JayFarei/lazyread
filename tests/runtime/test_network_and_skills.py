from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from lazyread.config import Settings
from lazyread.network import expose_tailscale
from lazyread.skills import install_skills


def test_skill_installer_places_both_portable_skills_in_each_host_root(
    tmp_path: Path,
) -> None:
    codex = tmp_path / ".codex" / "skills"
    claude = tmp_path / ".claude" / "skills"

    result = install_skills([codex, claude])

    assert set(result["installed"]) == {
        str(codex / "lazyread"),
        str(codex / "defuddle"),
        str(claude / "lazyread"),
        str(claude / "defuddle"),
    }
    assert result["retired"] == []
    assert (codex / "lazyread" / "agents" / "openai.yaml").is_file()
    assert (claude / "defuddle" / "SKILL.md").is_file()


def test_skill_installer_does_not_silently_overwrite_existing_skills(
    tmp_path: Path,
) -> None:
    root = tmp_path / "skills"
    existing = root / "lazyread" / "SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("custom")

    with pytest.raises(FileExistsError, match="--force"):
        install_skills([root])

    assert existing.read_text() == "custom"


def test_forced_skill_install_replaces_symlink_without_touching_its_target(
    tmp_path: Path,
) -> None:
    codex = tmp_path / ".codex" / "skills"
    shared = tmp_path / "shared" / "defuddle"
    shared.mkdir(parents=True)
    (shared / "SKILL.md").write_text("old", encoding="utf-8")
    codex.mkdir(parents=True)
    (codex / "defuddle").symlink_to(shared)

    install_skills([codex], force=True)

    assert not (codex / "defuddle").is_symlink()
    assert (codex / "defuddle" / "SKILL.md").read_text(encoding="utf-8") != "old"
    assert (shared / "SKILL.md").read_text(encoding="utf-8") == "old"


def test_forced_skill_install_retires_both_legacy_skill_names(tmp_path: Path) -> None:
    root = tmp_path / ".codex" / "skills"
    previous = root / "lazyreader"
    oldest = root / "listen-read"
    previous.mkdir(parents=True)
    oldest.mkdir(parents=True)
    (previous / "SKILL.md").write_text("lazyreader notes", encoding="utf-8")
    (oldest / "SKILL.md").write_text("listen read notes", encoding="utf-8")
    (root / "defuddle").mkdir()

    result = install_skills([root], force=True)

    previous_backup = root / ".lazyreader-backup"
    oldest_backup = root / ".listen-read-backup"
    assert result["retired"] == [str(previous_backup), str(oldest_backup)]
    assert not previous.exists()
    assert not oldest.exists()
    assert (previous_backup / "SKILL.md").read_text(encoding="utf-8") == "lazyreader notes"
    assert (oldest_backup / "SKILL.md").read_text(encoding="utf-8") == "listen read notes"
    assert (root / "lazyread" / "SKILL.md").is_file()


def test_skill_install_preflights_legacy_backups_across_all_roots(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "lazyreader").mkdir(parents=True)
        (root / "lazyreader" / "SKILL.md").write_text("legacy", encoding="utf-8")
    (second / ".lazyreader-backup").mkdir()

    with pytest.raises(FileExistsError, match="backups already exist"):
        install_skills([first, second], force=True)

    assert (first / "lazyreader" / "SKILL.md").read_text(encoding="utf-8") == "legacy"
    assert not (first / "lazyread").exists()
    assert not (first / ".lazyreader-backup").exists()


def test_tailscale_exposure_adds_only_the_requested_unused_port(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["tailscale", "serve", "status"]:
            output = {
                "Web": {
                    "host.test.ts.net:7445": {
                        "Handlers": {"/": {"Proxy": "http://127.0.0.1:4244"}}
                    }
                }
            }
        elif command[:2] == ["tailscale", "status"]:
            output = {"Self": {"DNSName": "host.test.ts.net."}}
        else:
            output = {}
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    result = expose_tailscale(
        Settings(home=tmp_path / "home", port=4246),
        https_port=7447,
        runner=run,
        health_check=lambda _settings: True,
    )

    assert result == {
        "status": "exposed",
        "url": "https://host.test.ts.net:7447",
        "https_port": 7447,
    }
    assert ["tailscale", "serve", "reset"] not in calls
    assert ["tailscale", "serve", "--bg", "--yes", "--https=7447", "4246"] in calls


def test_tailscale_exposure_refuses_to_replace_an_unrelated_route(
    tmp_path: Path,
) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "Web": {
                        "host.test.ts.net:7447": {
                            "Handlers": {"/": {"Proxy": "http://127.0.0.1:9999"}}
                        }
                    }
                }
            ),
            "",
        )

    with pytest.raises(ValueError, match="already serves another"):
        expose_tailscale(
            Settings(home=tmp_path / "home", port=4246),
            https_port=7447,
            runner=run,
            health_check=lambda _settings: True,
        )


def test_tailscale_exposure_refuses_a_non_lazyread_local_port(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="refusing to expose"):
        expose_tailscale(
            Settings(home=tmp_path / "home", port=9999),
            https_port=7447,
            runner=lambda command, **kwargs: subprocess.CompletedProcess(
                command, 0, "{}", ""
            ),
            health_check=lambda _settings: False,
        )


def test_tailscale_exposure_refuses_an_existing_non_web_tcp_listener(
    tmp_path: Path,
) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"TCP": {"7447": {"TCPForward": "127.0.0.1:9999"}}}),
            "",
        )

    with pytest.raises(ValueError, match="already owned"):
        expose_tailscale(
            Settings(home=tmp_path / "home", port=4246),
            https_port=7447,
            runner=run,
            health_check=lambda _settings: True,
        )
