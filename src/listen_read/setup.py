from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable
import uuid

from . import __version__
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


def _packaged_file(relative: str) -> Path:
    packaged = Path(__file__).parent / relative
    checkout_relative = relative.replace("defuddle-package/", "defuddle/")
    checkout = Path(__file__).parents[2] / "packaging" / checkout_relative
    for candidate in (packaged, checkout):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"packaged dependency lock is missing: {relative}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    expected["app_version"] = __version__
    expected["worker_lock_sha256"] = _sha256(_packaged_file("worker-requirements.lock"))
    expected["defuddle_lock_sha256"] = _sha256(
        _packaged_file("defuddle-package/package-lock.json")
    )
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
    staging = runtime / f".setup-{uuid.uuid4().hex}"
    staged_defuddle = staging / "defuddle"
    staged_worker = staging / "worker"
    staged_defuddle.mkdir(parents=True)
    staged_worker.mkdir(parents=True)
    staged_python = staged_worker / ".venv" / "bin" / "python"
    try:
        shutil.copy2(
            _packaged_file("defuddle-package/package.json"), staged_defuddle / "package.json"
        )
        shutil.copy2(
            _packaged_file("defuddle-package/package-lock.json"),
            staged_defuddle / "package-lock.json",
        )

        result = runner(
            ["npm", "ci", "--prefix", str(staged_defuddle), "--omit=dev", "--ignore-scripts"],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        _check(result, "Defuddle installation")
        result = runner(
            ["uv", "venv", "--python", "3.12", str(staged_worker / ".venv")],
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
                str(staged_python),
                "--requirement",
                str(_packaged_file("worker-requirements.lock")),
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
                [str(staged_python), "-c", program],
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            _check(result, "model download")

        staged_defuddle_binary = (
            staged_defuddle / "node_modules" / ".bin" / "defuddle"
        )
        if not staged_python.is_file() or not staged_defuddle_binary.is_file():
            raise OSError("staged dependency installation did not produce runnable binaries")

        backups: list[tuple[Path, Path]] = []
        installed: list[Path] = []
        try:
            for name, staged in (("defuddle", staged_defuddle), ("worker", staged_worker)):
                target = runtime / name
                backup = runtime / f".{name}.previous"
                shutil.rmtree(backup, ignore_errors=True)
                if target.exists():
                    os.replace(target, backup)
                    backups.append((target, backup))
                os.replace(staged, target)
                installed.append(target)
        except BaseException:
            for target in reversed(installed):
                shutil.rmtree(target, ignore_errors=True)
            for target, backup in reversed(backups):
                if backup.exists():
                    os.replace(backup, target)
            raise
        for _, backup in backups:
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    marker_tmp = marker.with_suffix(".json.tmp")
    marker_tmp.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    os.replace(marker_tmp, marker)
    return {"status": "installed", **expected}
