from __future__ import annotations

import os
from pathlib import Path
import shutil

from .config import Settings
from .dispatcher import SerialProcessingDispatcher
from .pipeline import ArticleProcessor, DefuddleAdapter
from .runtime import Runtime
from .worker import FakeNarrationWorker, MlxTemplateWorkerAdapter


TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16"
TTS_REVISION = "52f4770fd9726457eae3d3b6aa92047a25a10776"
ALIGNER_MODEL = "mlx-community/Qwen3-ForcedAligner-0.6B-8bit"
ALIGNER_REVISION = "0e1a68e91d815300c7c9754b2a7639378b23db15"
MLX_AUDIO_REVISION = "64e8416c303fb3b3463dab8eb4ebd78c55a87c1a"


def _template_source() -> Path:
    packaged = Path(__file__).parent / "worker_template"
    checkout = Path(__file__).parents[2] / "assets" / "reader-template"
    for candidate in (packaged, checkout):
        if (candidate / "scripts" / "generate_audio.py").is_file():
            return candidate
    raise FileNotFoundError("Lazyread's narration worker template is missing")


def _article_worker_project(home: Path, article_id: str) -> Path:
    destination = home / "runtime" / "jobs" / article_id
    script = destination / "scripts" / "generate_audio.py"
    if not script.is_file():
        source = _template_source()
        script.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "scripts" / "generate_audio.py", script)
        (destination / "src" / "generated").mkdir(parents=True, exist_ok=True)
        (destination / "public" / "audio").mkdir(parents=True, exist_ok=True)
        (destination / "tmp" / "audio").mkdir(parents=True, exist_ok=True)
    return destination


def create_runtime(
    settings: Settings,
    *,
    worker_mode: str | None = None,
    resume_pending: bool = True,
) -> tuple[Runtime, SerialProcessingDispatcher]:
    """Build the durable runtime and its serial, restart-safe processing queue."""

    mode = (
        worker_mode
        or os.environ.get("LAZYREAD_WORKER")
        or os.environ.get("LAZYREADER_WORKER")
        or os.environ.get("LISTEN_READ_WORKER")
        or "mlx"
    ).casefold()

    def processor(article_id: str) -> ArticleProcessor:
        if mode == "fake":
            worker = FakeNarrationWorker()
        elif mode == "mlx":
            project = _article_worker_project(settings.home, article_id)
            worker_python = (
                settings.home / "runtime" / "worker" / ".venv" / "bin" / "python"
            )
            environment = {
                **os.environ,
                "HF_HOME": str(settings.home / "cache" / "models"),
                "LAZYREAD_CHUNK_CACHE": str(settings.home / "cache" / "chunks"),
                "LAZYREAD_TTS_REVISION": TTS_REVISION,
                "LAZYREAD_ALIGNER_REVISION": ALIGNER_REVISION,
            }
            worker = MlxTemplateWorkerAdapter(
                project_root=project,
                command=[
                    str(worker_python),
                    str(project / "scripts" / "generate_audio.py"),
                ],
                environment=environment,
            )
        else:
            raise ValueError("LAZYREAD_WORKER must be 'mlx' or 'fake'")

        managed_defuddle = (
            settings.home
            / "runtime"
            / "defuddle"
            / "node_modules"
            / ".bin"
            / "defuddle"
        )
        source_adapter = DefuddleAdapter(
            executable=str(managed_defuddle)
            if managed_defuddle.is_file()
            else "defuddle"
        )
        return ArticleProcessor(
            worker=worker,
            model_revision=TTS_REVISION if mode == "mlx" else "fake-tts-v1",
            aligner_revision=ALIGNER_REVISION if mode == "mlx" else "fake-aligner-v1",
            mlx_audio_revision=(
                MLX_AUDIO_REVISION if mode == "mlx" else "fake-mlx-audio-v1"
            ),
            source_adapter=source_adapter,
        )

    dispatcher = SerialProcessingDispatcher(processor)
    runtime = Runtime(settings, dispatcher=dispatcher)
    dispatcher.bind(runtime)
    if resume_pending:
        dispatcher.resume_pending()
    return runtime, dispatcher
