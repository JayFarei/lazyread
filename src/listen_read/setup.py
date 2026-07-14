from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable

from .app import (
    ALIGNER_MODEL,
    ALIGNER_REVISION,
    MLX_AUDIO_REVISION,
    TTS_MODEL,
    TTS_REVISION,
)
from .config import Settings


DEFUDDLE_VERSION = "0.19.1"
MODEL_DOWNLOAD_GB = 5.4
Runner = Callable[..., subprocess.CompletedProcess[str]]


def setup_plan(settings: Settings) -> dict[str, Any]:
    return {
        "requires_confirmation": True,
        "home": str(settings.home),
        "platform": "macOS arm64",
        "model_download_gb": MODEL_DOWNLOAD_GB,
        "working_disk_gb": 8,
        "defuddle_version": DEFUDDLE_VERSION,
        "mlx_audio_revision": MLX_AUDIO_REVISION,
        "tts_model": TTS_MODEL,
        "tts_revision": TTS_REVISION,
        "aligner_model": ALIGNER_MODEL,
        "aligner_revision": ALIGNER_REVISION,
        "note": (
            "Installs an app-owned Python worker and Defuddle CLI, then downloads "
            "the pinned local speech and alignment models. Global npm packages are untouched."
        ),
    }


def _check(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise OSError(f"{label} failed: {detail}")


def install_dependencies(
    settings: Settings,
    *,
    runner: Runner = subprocess.run,
    download_models: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Install pinned dependencies into Application Support, never global state."""

    settings.ensure_directories()
    runtime = settings.home / "runtime"
    marker = runtime / "setup.json"
    expected = {key: value for key, value in setup_plan(settings).items() if key not in {"requires_confirmation", "note"}}
    expected["models_downloaded"] = download_models
    defuddle_binary = runtime / "defuddle" / "node_modules" / ".bin" / "defuddle"
    worker_python = runtime / "worker" / ".venv" / "bin" / "python"
    models_present = any((settings.home / "cache" / "models").iterdir())
    if marker.is_file() and worker_python.is_file() and defuddle_binary.is_file() and not force:
        try:
            if json.loads(marker.read_text(encoding="utf-8")) == expected and (
                not download_models or models_present
            ):
                return {"status": "already_ready", **expected}
        except (OSError, json.JSONDecodeError):
            pass

    environment = {**os.environ, "HF_HOME": str(settings.home / "cache" / "models")}
    defuddle_root = runtime / "defuddle"
    worker_root = runtime / "worker"
    defuddle_root.mkdir(parents=True, exist_ok=True)
    worker_root.mkdir(parents=True, exist_ok=True)

    result = runner(
        ["npm", "install", "--prefix", str(defuddle_root), f"defuddle@{DEFUDDLE_VERSION}"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    _check(result, "Defuddle installation")
    result = runner(
        ["uv", "venv", "--python", "3.12", str(worker_root / ".venv")],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    _check(result, "worker environment creation")
    result = runner(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(worker_python),
            f"mlx-audio @ git+https://github.com/Blaizzy/mlx-audio.git@{MLX_AUDIO_REVISION}",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    _check(result, "MLX worker installation")

    if download_models:
        program = (
            "from huggingface_hub import snapshot_download;"
            f"snapshot_download({TTS_MODEL!r}, revision={TTS_REVISION!r});"
            f"snapshot_download({ALIGNER_MODEL!r}, revision={ALIGNER_REVISION!r})"
        )
        result = runner(
            [str(worker_python), "-c", program],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        _check(result, "model download")

    marker.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    return {"status": "installed", **expected}
