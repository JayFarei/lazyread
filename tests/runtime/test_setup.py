from __future__ import annotations

import json
from pathlib import Path
import subprocess

from listen_read.cli import main
from listen_read.config import Settings
from listen_read.setup import DEFUDDLE_VERSION, install_dependencies, setup_plan


def test_setup_requires_explicit_confirmation_before_large_downloads(tmp_path: Path) -> None:
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


def test_setup_is_idempotent_after_its_revision_marker_is_written(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    installed = install_dependencies(settings, runner=run, download_models=False)
    worker_python = settings.home / "runtime" / "worker" / ".venv" / "bin" / "python"
    defuddle = settings.home / "runtime" / "defuddle" / "node_modules" / ".bin" / "defuddle"
    worker_python.parent.mkdir(parents=True)
    defuddle.parent.mkdir(parents=True)
    worker_python.touch()
    defuddle.touch()
    repeated = install_dependencies(settings, runner=run, download_models=False)

    assert installed["status"] == "installed"
    assert repeated["status"] == "already_ready"
    assert len(calls) == 3
    assert calls[0][-1] == f"defuddle@{DEFUDDLE_VERSION}"
    assert setup_plan(settings)["mlx_audio_revision"]
