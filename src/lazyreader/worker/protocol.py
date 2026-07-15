from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping, Protocol, TextIO

if TYPE_CHECKING:
    from lazyreader.pipeline import PreparedDocument


PROTOCOL_VERSION = 2


@dataclass(frozen=True, slots=True)
class NarrationWord:
    id: str
    text: str
    ordinal: int
    display_word_id: str | None = None
    sentence_end: bool = False
    sentence_suffix: str = ""


@dataclass(frozen=True, slots=True)
class NarrationChunk:
    id: str
    ordinal: int
    text: str
    words: tuple[NarrationWord, ...]


@dataclass(frozen=True, slots=True)
class NarrationRequest:
    job_id: str
    projection_id: str
    chunks: tuple[NarrationChunk, ...]
    voice: str
    settings: Mapping[str, Any]
    model_revision: str
    aligner_revision: str
    mlx_audio_revision: str
    protocol_version: int = PROTOCOL_VERSION

    @classmethod
    def from_prepared(
        cls,
        *,
        job_id: str,
        prepared: PreparedDocument,
        voice: str,
        settings: Mapping[str, Any],
        model_revision: str,
        aligner_revision: str,
        mlx_audio_revision: str,
    ) -> NarrationRequest:
        return cls(
            job_id=job_id,
            projection_id=prepared.speech.projection_id,
            chunks=tuple(
                NarrationChunk(
                    id=chunk.id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    words=tuple(
                        NarrationWord(
                            id=word.id,
                            text=word.text,
                            ordinal=word.ordinal,
                            display_word_id=word.display_word_id,
                            sentence_end=word.sentence_end,
                            sentence_suffix=word.sentence_suffix,
                        )
                        for word in chunk.words
                    ),
                )
                for chunk in prepared.speech.chunks
            ),
            voice=voice,
            settings=dict(settings),
            model_revision=model_revision,
            aligner_revision=aligner_revision,
            mlx_audio_revision=mlx_audio_revision,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> NarrationRequest:
        raw = json.loads(value)
        version = int(raw.get("protocol_version", 0))
        if version != PROTOCOL_VERSION:
            raise ValueError(
                f"Unsupported worker protocol {version}; expected {PROTOCOL_VERSION}."
            )
        return cls(
            job_id=str(raw["job_id"]),
            projection_id=str(raw["projection_id"]),
            chunks=tuple(
                NarrationChunk(
                    id=str(chunk["id"]),
                    ordinal=int(chunk["ordinal"]),
                    text=str(chunk["text"]),
                    words=tuple(
                        NarrationWord(
                            id=str(word["id"]),
                            text=str(word["text"]),
                            ordinal=int(word["ordinal"]),
                            display_word_id=(
                                str(word["display_word_id"])
                                if word.get("display_word_id") is not None
                                else None
                            ),
                            sentence_end=bool(word.get("sentence_end", False)),
                            sentence_suffix=str(word.get("sentence_suffix", "")),
                        )
                        for word in chunk.get("words", ())
                    ),
                )
                for chunk in raw.get("chunks", ())
            ),
            voice=str(raw["voice"]),
            settings=dict(raw.get("settings", {})),
            model_revision=str(raw["model_revision"]),
            aligner_revision=str(raw["aligner_revision"]),
            mlx_audio_revision=str(raw["mlx_audio_revision"]),
            protocol_version=version,
        )


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    job_id: str
    sequence: int
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    protocol_version: int = PROTOCOL_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> WorkerEvent:
        raw = json.loads(value)
        version = int(raw.get("protocol_version", 0))
        if version != PROTOCOL_VERSION:
            raise ValueError(
                f"Unsupported worker protocol {version}; expected {PROTOCOL_VERSION}."
            )
        return cls(
            job_id=str(raw["job_id"]),
            sequence=int(raw["sequence"]),
            type=str(raw["type"]),
            payload=dict(raw.get("payload", {})),
            protocol_version=version,
        )


class NarrationWorker(Protocol):
    def run(self, request: NarrationRequest) -> Iterable[WorkerEvent]: ...


class FakeNarrationWorker:
    """Deterministic worker for runtime, recovery, and UI tests."""

    def __init__(self, *, seconds_per_word: float = 0.2) -> None:
        if seconds_per_word <= 0:
            raise ValueError("seconds_per_word must be positive")
        self._seconds_per_word = seconds_per_word

    def run(self, request: NarrationRequest) -> Iterator[WorkerEvent]:
        sequence = 0

        def event(type_: str, **payload: Any) -> WorkerEvent:
            nonlocal sequence
            result = WorkerEvent(request.job_id, sequence, type_, payload)
            sequence += 1
            return result

        yield event(
            "worker_started",
            chunk_total=len(request.chunks),
            model_revision=request.model_revision,
            aligner_revision=request.aligner_revision,
            mlx_audio_revision=request.mlx_audio_revision,
        )
        elapsed = 0.0
        word_count = 0
        for chunk in request.chunks:
            yield event("chunk_started", chunk_id=chunk.id, chunk=chunk.ordinal)
            timings: list[dict[str, Any]] = []
            for word in chunk.words:
                start = elapsed
                elapsed += self._seconds_per_word
                timings.append(
                    {
                        "word_id": word.id,
                        "text": word.text,
                        "start": round(start, 6),
                        "end": round(elapsed, 6),
                    }
                )
                word_count += 1
            yield event(
                "chunk_completed",
                chunk_id=chunk.id,
                chunk=chunk.ordinal,
                duration_seconds=round(len(chunk.words) * self._seconds_per_word, 6),
                timings=timings,
                cache_hit=False,
            )
        yield event("validation_completed", valid=True, repair_stage=None)
        yield event(
            "worker_completed",
            duration_seconds=round(elapsed, 6),
            word_count=word_count,
            chunk_count=len(request.chunks),
        )


def run_jsonl_worker(
    input_stream: TextIO,
    output_stream: TextIO,
    worker: NarrationWorker,
) -> None:
    """Run one or more requests over the line-delimited process seam."""

    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = NarrationRequest.from_json(line)
            events = worker.run(request)
            for event in events:
                output_stream.write(event.to_json() + "\n")
                output_stream.flush()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            event = WorkerEvent(
                job_id="unknown",
                sequence=0,
                type="protocol_error",
                payload={
                    "message": f"Invalid worker request: {type(exc).__name__}",
                    "retryable": False,
                },
            )
            output_stream.write(event.to_json() + "\n")
            output_stream.flush()
