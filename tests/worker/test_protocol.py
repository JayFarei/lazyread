from __future__ import annotations

from io import StringIO
import json

from listen_read.pipeline import DocumentPipeline, acquire_markdown
from listen_read.worker import (
    FakeNarrationWorker,
    NarrationRequest,
    WorkerEvent,
    run_jsonl_worker,
)


def request() -> NarrationRequest:
    prepared = DocumentPipeline(max_chunk_words=3).prepare(
        acquire_markdown("One two three four five."),
    )
    return NarrationRequest.from_prepared(
        job_id="job-7",
        prepared=prepared,
        voice="Aiden",
        settings={"style": "warm", "speed": 1.0},
        model_revision="tts@abc123",
        aligner_revision="aligner@def456",
        mlx_audio_revision="mlx-audio@fedcba",
    )


def test_worker_request_round_trips_as_one_jsonl_record() -> None:
    original = request()

    restored = NarrationRequest.from_json(original.to_json())

    assert restored == original
    assert original.to_json().count("\n") == 0
    assert [chunk.ordinal for chunk in original.chunks] == [0, 1]


def test_fake_worker_emits_deterministic_ordered_events() -> None:
    events = list(FakeNarrationWorker(seconds_per_word=0.25).run(request()))

    assert [event.type for event in events] == [
        "worker_started",
        "chunk_started",
        "chunk_completed",
        "chunk_started",
        "chunk_completed",
        "validation_completed",
        "worker_completed",
    ]
    assert [event.sequence for event in events] == list(range(len(events)))
    assert events[-1].payload["duration_seconds"] == 1.25
    assert events[-1].payload["word_count"] == 5
    assert events == list(FakeNarrationWorker(seconds_per_word=0.25).run(request()))


def test_jsonl_process_seam_returns_events_and_structured_errors() -> None:
    valid = request().to_json()
    input_stream = StringIO(valid + "\n" + "not-json\n")
    output_stream = StringIO()

    run_jsonl_worker(input_stream, output_stream, FakeNarrationWorker())

    records = [json.loads(line) for line in output_stream.getvalue().splitlines()]
    assert records[0]["type"] == "worker_started"
    assert records[-1]["type"] == "protocol_error"
    assert records[-1]["payload"]["retryable"] is False
    assert "not-json" not in records[-1]["payload"]["message"]


def test_worker_event_json_contract_is_versioned() -> None:
    event = WorkerEvent(
        job_id="job-1", sequence=2, type="chunk_completed", payload={"chunk": 1}
    )

    restored = WorkerEvent.from_json(event.to_json())

    assert restored == event
    assert json.loads(event.to_json())["protocol_version"] == 2
