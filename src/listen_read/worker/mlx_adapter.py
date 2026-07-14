from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit

from .protocol import NarrationRequest, WorkerEvent
from .validation import NarrationTiming, TimingBounds, validate_timings


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class MlxTemplateWorkerAdapter:
    """Run the proven reader-template MLX stack behind a subprocess boundary.

    Importing this module never imports MLX, NumPy, or model code. The adapter
    materializes the legacy ``article.json`` shape, executes the current
    ``scripts/generate_audio.py``, and translates its manifest into worker events.
    """

    def __init__(
        self,
        *,
        project_root: Path,
        runner: Runner = subprocess.run,
        command: list[str] | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._runner = runner
        self._command = command or [
            str(self._project_root / "scripts" / "generate_audio.py")
        ]
        self._environment = environment

    def run(self, request: NarrationRequest) -> Iterator[WorkerEvent]:
        yield WorkerEvent(
            request.job_id,
            0,
            "worker_started",
            {
                "chunk_total": len(request.chunks),
                "model_revision": request.model_revision,
                "aligner_revision": request.aligner_revision,
            },
        )
        self._write_legacy_article(request)
        yield WorkerEvent(request.job_id, 1, "mlx_process_started", {})
        try:
            arguments: dict[str, Any] = {
                "cwd": self._project_root,
                "capture_output": True,
                "text": True,
                "check": False,
            }
            if self._environment is not None:
                arguments["env"] = self._environment
            result = self._runner(list(self._command), **arguments)
        except OSError as exc:
            yield WorkerEvent(
                request.job_id,
                2,
                "worker_failed",
                {
                    "message": f"MLX worker could not start: {type(exc).__name__}",
                    "retryable": True,
                    "repair_stage": "synthesis",
                },
            )
            return
        if result.returncode != 0:
            yield WorkerEvent(
                request.job_id,
                2,
                "worker_failed",
                {
                    "message": f"MLX worker exited with status {result.returncode}.",
                    "retryable": True,
                    "repair_stage": "synthesis",
                },
            )
            return

        try:
            manifest = json.loads(
                (self._project_root / "public" / "audio" / "timings.json").read_text()
            )
            self._verify_provenance(request, manifest)
            report = self._validate_manifest(request, manifest)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            yield WorkerEvent(
                request.job_id,
                2,
                "worker_failed",
                {
                    "message": f"MLX output failed validation: {type(exc).__name__}",
                    "retryable": True,
                    "repair_stage": "synthesis",
                },
            )
            return
        if not report.valid:
            yield WorkerEvent(
                request.job_id,
                2,
                "worker_failed",
                {
                    "message": "MLX output did not pass the timing publication gate.",
                    "retryable": True,
                    "repair_stage": report.repair_stage,
                    "issue_codes": sorted({issue.code for issue in report.issues}),
                },
            )
            return

        yield WorkerEvent(
            request.job_id,
            2,
            "validation_completed",
            {"valid": True, "repair_stage": None},
        )
        yield WorkerEvent(
            request.job_id,
            3,
            "worker_completed",
            {
                "audio_url": str(manifest["audio"]),
                "timings_url": "/audio/timings.json",
                "audio_path": str(
                    self._project_root
                    / "public"
                    / "audio"
                    / Path(urlsplit(str(manifest["audio"])).path).name
                ),
                "timings_path": str(
                    self._project_root / "public" / "audio" / "timings.json"
                ),
                "duration_seconds": float(manifest["duration"]),
                "word_count": len(manifest["words"]),
            },
        )

    def _write_legacy_article(self, request: NarrationRequest) -> None:
        words: list[dict[str, Any]] = []
        chunks: list[dict[str, Any]] = []
        global_index = 0
        for chunk in request.chunks:
            first = global_index
            for word in chunk.words:
                words.append(
                    {"index": global_index, "text": word.text, "chunkIndex": chunk.ordinal}
                )
                global_index += 1
            chunks.append(
                {
                    "index": chunk.ordinal,
                    "text": chunk.text,
                    "firstWordIndex": first,
                    "lastWordIndex": global_index - 1,
                    "kind": "p",
                }
            )
        payload = {
            "metadata": {
                "title": request.projection_id,
                "author": "",
                "site": "",
                "source": "",
                "description": "",
                "published": "",
                "wordCount": len(words),
            },
            "html": "",
            "words": words,
            "chunks": chunks,
        }
        _atomic_json(
            self._project_root / "src" / "generated" / "article.json", payload
        )

    @staticmethod
    def _verify_provenance(
        request: NarrationRequest, manifest: dict[str, Any]
    ) -> None:
        expected = (
            request.voice,
            request.model_revision,
            request.aligner_revision,
        )
        actual = (
            manifest.get("voice"),
            manifest.get("modelRevision"),
            manifest.get("alignerRevision"),
        )
        if actual != expected:
            raise ValueError("MLX manifest provenance does not match the pinned request")

    @staticmethod
    def _validate_manifest(request: NarrationRequest, manifest: dict[str, Any]):
        flat_words = tuple(word for chunk in request.chunks for word in chunk.words)
        chunk_by_word = {
            word.id: chunk.id for chunk in request.chunks for word in chunk.words
        }
        duration = float(manifest["duration"])
        timings = tuple(
            NarrationTiming(
                word_id=flat_words[index].id,
                text=str(raw["text"]),
                start=float(raw["start"]),
                end=float(raw["end"]),
                chunk_id=chunk_by_word[flat_words[index].id],
            )
            for index, raw in enumerate(manifest["words"])
            if index < len(flat_words)
        )
        # The legacy manifest has global timings but no per-chunk audio offsets.
        # Until the native worker writes them, final-track bounds remain the
        # conservative chunk bound and identity/monotonicity still gate publish.
        bounds = {
            chunk.id: TimingBounds(0.0, duration) for chunk in request.chunks
        }
        return validate_timings(
            timings,
            expected_words=flat_words,
            audio_duration=duration,
            chunk_bounds=bounds,
        )
