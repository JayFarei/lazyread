from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import tempfile
import time
from typing import Any, Callable, Mapping, Protocol
import wave

from .acquisition import AcquiredDocument, SourceAcquisitionError, acquire_markdown
from .documents import DocumentPipeline, PreparedDocument, ScientificPolicy
from lazyreader.worker.protocol import NarrationRequest, NarrationWorker
from lazyreader.worker.validation import (
    NarrationTiming,
    TimingBounds,
    validate_timings,
)


TransitionCallback = Callable[[str, Mapping[str, Any]], None]


class SourceAdapter(Protocol):
    def acquire(self, url: str) -> AcquiredDocument: ...


class ArticleProcessingError(RuntimeError):
    """An article failed before its validated narration could be published."""


@dataclass(frozen=True, slots=True)
class ArticleProcessingResult:
    article_id: str
    audio_filename: str
    timings_filename: str
    duration_seconds: float
    word_count: int
    model_revision: str
    aligner_revision: str

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    os.close(descriptor)
    try:
        shutil.copyfile(source, temporary)
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class ArticleProcessor:
    """Runtime integration seam for canonicalization and narration publication.

    ``transition(state, payload)`` intentionally mirrors
    ``Runtime.transition_job`` so the dispatcher can pass it directly.
    """

    def __init__(
        self,
        *,
        worker: NarrationWorker,
        voice: str = "Aiden",
        settings: Mapping[str, Any] | None = None,
        model_revision: str,
        aligner_revision: str,
        mlx_audio_revision: str,
        max_chunk_words: int = 120,
        policy: ScientificPolicy | None = None,
        source_adapter: SourceAdapter | None = None,
    ) -> None:
        self._worker = worker
        self._voice = voice
        self._settings = dict(settings or {})
        self._model_revision = model_revision
        self._aligner_revision = aligner_revision
        self._mlx_audio_revision = mlx_audio_revision
        self._pipeline = DocumentPipeline(max_chunk_words=max_chunk_words)
        self._policy = policy or ScientificPolicy()
        self._source_adapter = source_adapter

    def cancel(self) -> None:
        cancel = getattr(self._worker, "cancel", None)
        if callable(cancel):
            cancel()

    def cleanup(self) -> None:
        cleanup = getattr(self._worker, "cleanup", None)
        if callable(cleanup):
            cleanup()

    def process(
        self,
        article_id: str,
        home: Path,
        transition: TransitionCallback,
        *,
        source_url: str | None = None,
    ) -> ArticleProcessingResult:
        started = time.perf_counter()
        self_usage = resource.getrusage(resource.RUSAGE_SELF)
        child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        article_dir = Path(home) / "articles" / article_id
        source_path = article_dir / "source.md"
        document_path = article_dir / "document.json"
        transition("canonicalizing", {"phase": "canonicalizing"})
        if document_path.is_file():
            prepared = PreparedDocument.from_dict(
                json.loads(document_path.read_text(encoding="utf-8"))
            )
        else:
            acquired = self._acquire(source_path, source_url)
            prepared = self._pipeline.prepare(acquired, self._policy)
            _atomic_json(document_path, prepared.to_dict())
        _atomic_json(article_dir / "speech.json", asdict(prepared.speech))
        transition(
            "text_ready",
            {
                "phase": "text_ready",
                "completed": 0,
                "total": len(prepared.speech.chunks),
                "title": prepared.display.title,
            },
        )

        request = NarrationRequest.from_prepared(
            job_id=article_id,
            prepared=prepared,
            voice=self._voice,
            settings=self._settings,
            model_revision=self._model_revision,
            aligner_revision=self._aligner_revision,
            mlx_audio_revision=self._mlx_audio_revision,
        )
        timing_records: list[dict[str, Any]] = []
        completion: Mapping[str, Any] | None = None
        worker_validated = False
        chunks_complete = 0
        for event in self._worker.run(request):
            if event.type == "chunk_completed":
                chunks_complete += 1
                for timing in event.payload.get("timings", ()):
                    timing_records.append(
                        {
                            **dict(timing),
                            "chunk_id": event.payload.get("chunk_id"),
                        }
                    )
                transition(
                    "narrating",
                    {
                        "phase": "narrating",
                        "completed": chunks_complete,
                        "total": len(request.chunks),
                    },
                )
            elif event.type == "worker_failed":
                transition(
                    "failed",
                    {
                        "phase": "failed",
                        "error": str(event.payload.get("message", "Worker failed")),
                        "resumable": bool(event.payload.get("retryable", False)),
                    },
                )
                raise ArticleProcessingError(
                    str(event.payload.get("message", "Worker failed"))
                )
            elif event.type == "validation_completed":
                worker_validated = bool(event.payload.get("valid", False))
            elif event.type == "worker_completed":
                completion = event.payload

        if completion is None:
            transition(
                "failed",
                {
                    "phase": "failed",
                    "error": "Worker returned no completion event.",
                    "resumable": True,
                },
            )
            raise ArticleProcessingError("Worker returned no completion event.")
        if not worker_validated:
            transition(
                "failed",
                {
                    "phase": "failed",
                    "error": "Worker output has no successful validation event.",
                    "resumable": True,
                },
            )
            raise ArticleProcessingError(
                "Worker output cannot be published without successful validation."
            )

        transition(
            "validating",
            {
                "phase": "validating",
                "completed": len(request.chunks),
                "total": len(request.chunks),
            },
        )
        if completion.get("audio_path") and completion.get("timings_path"):
            result = self._publish_real_artifacts(
                article_id, article_dir, completion, request
            )
        else:
            try:
                self._validate_fake_timings(request, completion, timing_records)
            except (ArticleProcessingError, KeyError, TypeError, ValueError) as exc:
                transition(
                    "failed",
                    {
                        "phase": "failed",
                        "error": str(exc),
                        "resumable": True,
                    },
                )
                if isinstance(exc, ArticleProcessingError):
                    raise
                raise ArticleProcessingError(
                    "Worker timing validation failed."
                ) from exc
            result = self._publish_fake_artifacts(
                article_id, article_dir, completion, timing_records, request
            )
        final_self = resource.getrusage(resource.RUSAGE_SELF)
        final_child = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak_rss = max(final_self.ru_maxrss, final_child.ru_maxrss)
        if platform.system() != "Darwin":
            peak_rss *= 1024
        telemetry_path = article_dir / "telemetry.json"
        existing: dict[str, Any] = {}
        if telemetry_path.is_file():
            try:
                existing = json.loads(telemetry_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        _atomic_json(
            telemetry_path,
            {
                **existing,
                "wall_seconds": round(time.perf_counter() - started, 6),
                "self_cpu_seconds": round(
                    (final_self.ru_utime + final_self.ru_stime)
                    - (self_usage.ru_utime + self_usage.ru_stime),
                    6,
                ),
                "child_cpu_seconds": round(
                    (final_child.ru_utime + final_child.ru_stime)
                    - (child_usage.ru_utime + child_usage.ru_stime),
                    6,
                ),
                "peak_rss_bytes": int(peak_rss),
                "worker": type(self._worker).__name__,
                "model_revision": self._model_revision,
                "aligner_revision": self._aligner_revision,
                "mlx_audio_revision": self._mlx_audio_revision,
                "audio_seconds": result.duration_seconds,
                "word_count": result.word_count,
            },
        )
        transition(
            "ready",
            {
                "phase": "ready",
                "completed": len(request.chunks),
                "total": len(request.chunks),
            },
        )
        return result

    @staticmethod
    def _validate_fake_timings(
        request: NarrationRequest,
        completion: Mapping[str, Any],
        timings: list[dict[str, Any]],
    ) -> None:
        duration = float(completion["duration_seconds"])
        if duration <= 0:
            raise ArticleProcessingError("Worker returned non-positive audio duration.")
        expected_words = tuple(word for chunk in request.chunks for word in chunk.words)
        parsed = tuple(
            NarrationTiming(
                word_id=str(item["word_id"]),
                text=str(item["text"]),
                start=float(item["start"]),
                end=float(item["end"]),
                chunk_id=str(item["chunk_id"]),
            )
            for item in timings
        )
        conservative_bounds = {
            chunk.id: TimingBounds(0.0, duration) for chunk in request.chunks
        }
        report = validate_timings(
            parsed,
            expected_words=expected_words,
            audio_duration=duration,
            chunk_bounds=conservative_bounds,
        )
        if not report.valid:
            codes = ", ".join(sorted({issue.code for issue in report.issues}))
            raise ArticleProcessingError(f"Worker timing validation failed: {codes}")

    def _acquire(self, source_path: Path, source_url: str | None) -> AcquiredDocument:
        markdown = source_path.read_text() if source_path.exists() else ""
        if markdown.strip():
            return acquire_markdown(
                markdown, **({"source_url": source_url} if source_url else {})
            )
        if source_url and self._source_adapter:
            acquired = self._source_adapter.acquire(source_url)
            _atomic_bytes(source_path, acquired.markdown.encode("utf-8"))
            return acquired
        raise SourceAcquisitionError(
            f"Article source is empty at {source_path}; provide Markdown or a URL adapter."
        )

    def _publish_fake_artifacts(
        self,
        article_id: str,
        article_dir: Path,
        completion: Mapping[str, Any],
        timings: list[dict[str, Any]],
        request: NarrationRequest,
    ) -> ArticleProcessingResult:
        duration = float(completion["duration_seconds"])
        sample_rate = 8_000
        descriptor, temporary = tempfile.mkstemp(prefix=".audio.wav.", dir=article_dir)
        os.close(descriptor)
        try:
            with wave.open(temporary, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(sample_rate)
                audio.writeframes(b"\x00\x00" * round(duration * sample_rate))
            os.replace(temporary, article_dir / "audio.wav")
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        manifest = {
            "audio": "audio.wav",
            "duration": duration,
            "sample_rate": sample_rate,
            "voice": self._voice,
            "model_revision": self._model_revision,
            "aligner_revision": self._aligner_revision,
            "mlx_audio_revision": self._mlx_audio_revision,
            "word_count": int(completion["word_count"]),
            "words": self._add_display_identity(timings, request),
        }
        _atomic_json(article_dir / "timings.json", manifest)
        return ArticleProcessingResult(
            article_id,
            "audio.wav",
            "timings.json",
            duration,
            int(completion["word_count"]),
            self._model_revision,
            self._aligner_revision,
        )

    def _publish_real_artifacts(
        self,
        article_id: str,
        article_dir: Path,
        completion: Mapping[str, Any],
        request: NarrationRequest,
    ) -> ArticleProcessingResult:
        source_audio = Path(str(completion["audio_path"]))
        source_timings = Path(str(completion["timings_path"]))
        suffix = source_audio.suffix or ".flac"
        audio_filename = f"audio{suffix}"
        _atomic_copy(source_audio, article_dir / audio_filename)
        manifest = json.loads(source_timings.read_text())
        manifest["audio"] = audio_filename
        manifest["words"] = self._add_display_identity(manifest["words"], request)
        _atomic_json(article_dir / "timings.json", manifest)
        generation = manifest.get("generationTelemetry")
        if isinstance(generation, Mapping):
            _atomic_json(article_dir / "telemetry.json", dict(generation))
        return ArticleProcessingResult(
            article_id,
            audio_filename,
            "timings.json",
            float(completion["duration_seconds"]),
            int(completion["word_count"]),
            self._model_revision,
            self._aligner_revision,
        )

    @staticmethod
    def _add_display_identity(
        timings: list[dict[str, Any]], request: NarrationRequest
    ) -> list[dict[str, Any]]:
        words = tuple(word for chunk in request.chunks for word in chunk.words)
        if len(timings) != len(words):
            raise ArticleProcessingError(
                f"Timing word count {len(timings)} does not match speech word count {len(words)}."
            )
        return [
            {
                **dict(timing),
                "word_id": word.id,
                "display_word_id": word.display_word_id,
                "sentence_end": word.sentence_end,
                "sentence_suffix": word.sentence_suffix,
            }
            for timing, word in zip(timings, words)
        ]
