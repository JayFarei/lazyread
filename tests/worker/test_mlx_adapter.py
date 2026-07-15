from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from lazyread.pipeline import DocumentPipeline, acquire_markdown
from lazyread.worker import MlxTemplateWorkerAdapter, NarrationRequest
from lazyread.worker.mlx_adapter import EVENT_PREFIX, LEGACY_EVENT_PREFIXES


def make_request() -> NarrationRequest:
    prepared = DocumentPipeline(max_chunk_words=2).prepare(
        acquire_markdown("One two three.")
    )
    return NarrationRequest.from_prepared(
        job_id="job-mlx",
        prepared=prepared,
        voice="Aiden",
        settings={"style": "warm"},
        model_revision="tts-sha",
        aligner_revision="aligner-sha",
        mlx_audio_revision="mlx-audio-sha",
    )


def test_mlx_adapter_materializes_legacy_input_and_runs_out_of_process(
    tmp_path: Path,
) -> None:
    script = tmp_path / "scripts" / "generate_audio.py"
    script.parent.mkdir(parents=True)
    script.write_text("raise AssertionError('runner must intercept this')\n")
    calls: list[tuple[list[str], Path]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cwd = Path(str(kwargs["cwd"]))
        calls.append((command, cwd))
        request = make_request()
        manifest_dir = cwd / "public" / "audio"
        manifest_dir.mkdir(parents=True)
        manifest = {
            "audio": "/audio/track.flac?v=123",
            "duration": 0.9,
            "voice": request.voice,
            "modelRevision": request.model_revision,
            "alignerRevision": request.aligner_revision,
            "mlxAudioRevision": request.mlx_audio_revision,
            "words": [
                {
                    "index": index,
                    "text": word.text,
                    "start": index * 0.3,
                    "end": (index + 1) * 0.3,
                }
                for index, word in enumerate(
                    word for chunk in request.chunks for word in chunk.words
                )
            ],
        }
        (manifest_dir / "timings.json").write_text(json.dumps(manifest))
        return subprocess.CompletedProcess(command, 0, "completed", "")

    events = list(
        MlxTemplateWorkerAdapter(project_root=tmp_path, runner=run).run(make_request())
    )

    assert calls == [([str(script)], tmp_path)]
    legacy = json.loads((tmp_path / "src" / "generated" / "article.json").read_text())
    assert [chunk["text"] for chunk in legacy["chunks"]] == ["One two", "three."]
    assert [word["text"] for word in legacy["words"]] == ["One", "two", "three"]
    assert [event.type for event in events] == [
        "worker_started",
        "mlx_process_started",
        "validation_completed",
        "worker_completed",
    ]
    assert events[-1].payload["audio_url"] == "/audio/track.flac?v=123"
    assert events[-1].payload["timings_url"] == "/audio/timings.json"


@pytest.mark.parametrize(
    ("mismatched_field", "different_value"),
    (("modelRevision", "different-sha"), ("mlxAudioRevision", "different-mlx-sha")),
)
def test_mlx_adapter_rejects_unpinned_manifest_provenance(
    tmp_path: Path, mismatched_field: str, different_value: str
) -> None:
    script = tmp_path / "scripts" / "generate_audio.py"
    script.parent.mkdir(parents=True)
    script.write_text("# intercepted\n")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cwd = Path(str(kwargs["cwd"]))
        output = cwd / "public" / "audio"
        output.mkdir(parents=True)
        manifest = {
            "audio": "/audio/track.flac",
            "duration": 1.0,
            "voice": "Aiden",
            "modelRevision": "tts-sha",
            "alignerRevision": "aligner-sha",
            "mlxAudioRevision": "mlx-audio-sha",
            "words": [],
        }
        manifest[mismatched_field] = different_value
        (output / "timings.json").write_text(json.dumps(manifest))
        return subprocess.CompletedProcess(command, 0, "", "")

    events = list(
        MlxTemplateWorkerAdapter(project_root=tmp_path, runner=run).run(make_request())
    )

    assert events[-1].type == "worker_failed"
    assert events[-1].payload["repair_stage"] == "synthesis"
    assert different_value not in events[-1].payload["message"]


def test_mlx_adapter_translates_streamed_chunk_progress_to_stable_identity() -> None:
    request = make_request()
    line = EVENT_PREFIX + json.dumps(
        {
            "type": "chunk_completed",
            "ordinal": 1,
            "duration_seconds": 0.42,
            "cache_hit": True,
            "synthesis_seconds": 0,
            "alignment_seconds": 0.12,
        }
    )

    event = MlxTemplateWorkerAdapter._progress_event(request, line, 7)

    assert event is not None
    assert event.sequence == 7
    assert event.type == "chunk_completed"
    assert event.payload["chunk_id"] == request.chunks[1].id
    assert event.payload["cache_hit"] is True

    for sequence, legacy_prefix in enumerate(LEGACY_EVENT_PREFIXES, start=8):
        legacy_event = MlxTemplateWorkerAdapter._progress_event(
            request, line.replace(EVENT_PREFIX, legacy_prefix, 1), sequence
        )
        assert legacy_event is not None
        assert legacy_event.sequence == sequence


def test_mlx_adapter_rejects_surplus_manifest_words(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "generate_audio.py"
    script.parent.mkdir(parents=True)
    script.write_text("# intercepted\n")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        request = make_request()
        output = Path(str(kwargs["cwd"])) / "public" / "audio"
        output.mkdir(parents=True)
        words = [
            {
                "index": index,
                "text": word.text,
                "start": index * 0.1,
                "end": (index + 1) * 0.1,
            }
            for index, word in enumerate(
                word for chunk in request.chunks for word in chunk.words
            )
        ]
        words.append({"index": 99, "text": "surplus", "start": 0.4, "end": 0.5})
        (output / "timings.json").write_text(
            json.dumps(
                {
                    "audio": "/audio/track.flac",
                    "duration": 1,
                    "voice": request.voice,
                    "modelRevision": request.model_revision,
                    "alignerRevision": request.aligner_revision,
                    "mlxAudioRevision": request.mlx_audio_revision,
                    "words": words,
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    events = list(
        MlxTemplateWorkerAdapter(project_root=tmp_path, runner=run).run(make_request())
    )

    assert events[-1].type == "worker_failed"


def test_mlx_adapter_cancel_terminates_a_blocked_process_group(tmp_path: Path) -> None:
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    adapter = MlxTemplateWorkerAdapter(
        project_root=tmp_path,
        command=[sys.executable, str(script)],
    )
    events: list = []
    thread = threading.Thread(target=lambda: events.extend(adapter.run(make_request())))
    started = time.monotonic()
    thread.start()
    while adapter._process is None and time.monotonic() - started < 3:  # noqa: SLF001
        time.sleep(0.01)

    adapter.cancel()
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert events[-1].type == "worker_failed"


def test_mlx_adapter_latches_cancel_before_the_process_is_spawned(
    tmp_path: Path,
) -> None:
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    adapter = MlxTemplateWorkerAdapter(
        project_root=tmp_path,
        command=[sys.executable, str(script)],
    )

    adapter.cancel()
    started = time.monotonic()
    events = list(adapter.run(make_request()))

    assert time.monotonic() - started < 3
    assert events[-1].type == "worker_failed"
