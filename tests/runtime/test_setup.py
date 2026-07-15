from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from lazyread.cli import main
from lazyread.config import Settings
from lazyread.setup import DEFUDDLE_VERSION, install_dependencies, setup_plan


def test_setup_requires_explicit_confirmation_before_large_downloads(
    tmp_path: Path,
) -> None:
    output: list[str] = []
    code = main(
        ["--home", str(tmp_path / "home"), "--json", "setup"],
        stdout=output.append,
    )
    plan = json.loads("".join(output))

    assert code == 3
    assert plan["requires_confirmation"] is True
    assert plan["model_download_gb"] >= 5
    assert plan["defuddle_version"] == DEFUDDLE_VERSION
    assert not (tmp_path / "home" / "runtime" / "worker" / ".venv").exists()


def test_setup_is_idempotent_after_its_revision_marker_is_written(
    tmp_path: Path,
) -> None:
    settings = Settings(home=tmp_path / "home")
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:2] == ["npm", "ci"]:
            prefix = Path(command[command.index("--prefix") + 1])
            binary = prefix / "node_modules" / ".bin" / "defuddle"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.touch()
        elif command[:2] == ["uv", "venv"]:
            python = Path(command[-1]) / "bin" / "python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.touch()
        return subprocess.CompletedProcess(command, 0, "", "")

    installed = install_dependencies(settings, runner=run, download_models=False)
    repeated = install_dependencies(settings, runner=run, download_models=False)

    assert installed["status"] == "installed"
    assert repeated["status"] == "already_ready"
    assert len(calls) == 3
    assert calls[0][:2] == ["npm", "ci"]
    assert calls[2][-2].endswith("--requirement")
    assert calls[2][-1].endswith("worker-requirements.lock")
    assert repeated["app_version"] == "0.1.0"
    assert len(repeated["worker_lock_sha256"]) == 64
    assert len(repeated["defuddle_lock_sha256"]) == 64
    assert setup_plan(settings)["mlx_audio_revision"]


def test_failed_upgrade_keeps_the_last_known_good_runtime(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    old_python = settings.home / "runtime" / "worker" / ".venv" / "bin" / "python"
    old_defuddle = (
        settings.home / "runtime" / "defuddle" / "node_modules" / ".bin" / "defuddle"
    )
    old_python.parent.mkdir(parents=True)
    old_defuddle.parent.mkdir(parents=True)
    old_python.write_text("old worker", encoding="utf-8")
    old_defuddle.write_text("old defuddle", encoding="utf-8")

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["npm", "ci"]:
            prefix = Path(command[command.index("--prefix") + 1])
            binary = prefix / "node_modules" / ".bin" / "defuddle"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.touch()
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["uv", "venv"]:
            python = Path(command[-1]) / "bin" / "python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.touch()
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 1, "", "network failed")

    with pytest.raises(OSError, match="MLX worker installation failed"):
        install_dependencies(settings, runner=run, download_models=False, force=True)

    assert old_python.read_text(encoding="utf-8") == "old worker"
    assert old_defuddle.read_text(encoding="utf-8") == "old defuddle"
