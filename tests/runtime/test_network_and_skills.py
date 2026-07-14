from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from listen_read.config import Settings
from listen_read.network import expose_tailscale
from listen_read.skills import install_skills


def test_skill_installer_places_both_portable_skills_in_each_host_root(tmp_path: Path) -> None:
    codex = tmp_path / ".codex" / "skills"
    claude = tmp_path / ".claude" / "skills"

    result = install_skills([codex, claude])

    assert set(result["installed"]) == {
        str(codex / "listen-read"),
        str(codex / "defuddle"),
        str(claude / "listen-read"),
        str(claude / "defuddle"),
    }
    assert (codex / "listen-read" / "agents" / "openai.yaml").is_file()
    assert (claude / "defuddle" / "SKILL.md").is_file()


def test_skill_installer_does_not_silently_overwrite_existing_skills(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    existing = root / "listen-read" / "SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("custom")

    with pytest.raises(FileExistsError, match="--force"):
        install_skills([root])

    assert existing.read_text() == "custom"


def test_tailscale_exposure_adds_only_the_requested_unused_port(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["tailscale", "serve", "status"]:
            output = {"Web": {"host.test.ts.net:7445": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:4244"}}}}}
        elif command[:2] == ["tailscale", "status"]:
            output = {"Self": {"DNSName": "host.test.ts.net."}}
        else:
            output = {}
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    result = expose_tailscale(
        Settings(home=tmp_path / "home", port=4246),
        https_port=7447,
        runner=run,
    )

    assert result == {
        "status": "exposed",
        "url": "https://host.test.ts.net:7447",
        "https_port": 7447,
    }
    assert ["tailscale", "serve", "reset"] not in calls
    assert ["tailscale", "serve", "--bg", "--yes", "--https=7447", "4246"] in calls


def test_tailscale_exposure_refuses_to_replace_an_unrelated_route(tmp_path: Path) -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {"Web": {"host.test.ts.net:7447": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:9999"}}}}}
            ),
            "",
        )

    with pytest.raises(ValueError, match="already serves another"):
        expose_tailscale(
            Settings(home=tmp_path / "home", port=4246),
            https_port=7447,
            runner=run,
        )
