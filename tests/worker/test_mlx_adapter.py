from __future__ import annotations

import json
from pathlib import Path
import subprocess

from listen_read.pipeline import DocumentPipeline, acquire_markdown
from listen_read.worker import MlxTemplateWorkerAdapter, NarrationRequest


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
            "words": [
                {"index": index, "text": word.text, "start": index * 0.3, "end": (index + 1) * 0.3}
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
    assert [chunk["text"] for chunk in legacy["chunks"]] == ["One two", "three"]
    assert [word["text"] for word in legacy["words"]] == ["One", "two", "three"]
    assert [event.type for event in events] == [
        "worker_started",
        "mlx_process_started",
        "validation_completed",
        "worker_completed",
    ]
    assert events[-1].payload["audio_url"] == "/audio/track.flac?v=123"
    assert events[-1].payload["timings_url"] == "/audio/timings.json"


def test_mlx_adapter_rejects_unpinned_manifest_provenance(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "generate_audio.py"
    script.parent.mkdir(parents=True)
    script.write_text("# intercepted\n")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cwd = Path(str(kwargs["cwd"]))
        output = cwd / "public" / "audio"
        output.mkdir(parents=True)
        (output / "timings.json").write_text(
            json.dumps(
                {
                    "audio": "/audio/track.flac",
                    "duration": 1.0,
                    "voice": "Aiden",
                    "modelRevision": "different-sha",
                    "alignerRevision": "aligner-sha",
                    "words": [],
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    events = list(
        MlxTemplateWorkerAdapter(project_root=tmp_path, runner=run).run(make_request())
    )

    assert events[-1].type == "worker_failed"
    assert events[-1].payload["repair_stage"] == "synthesis"
    assert "different-sha" not in events[-1].payload["message"]
