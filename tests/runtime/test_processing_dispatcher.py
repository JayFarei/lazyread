from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from listen_read.config import Settings
from listen_read.cli import main
from listen_read.dispatcher import SerialProcessingDispatcher
from listen_read.pipeline import ArticleProcessor
from listen_read.pipeline import DocumentPipeline, ScientificPolicy, acquire_markdown
from listen_read.runtime import Runtime
from listen_read.server import create_server
from listen_read.worker import FakeNarrationWorker
from listen_read.worker import WorkerEvent


def fake_processor(_article_id: str) -> ArticleProcessor:
    return ArticleProcessor(
        worker=FakeNarrationWorker(seconds_per_word=0.01),
        model_revision="test-tts-revision",
        aligner_revision="test-aligner-revision",
    )


def wait_for_state(runtime: Runtime, article_id: str, state: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = runtime.get_article(article_id)
        if current["job"]["state"] == state:
            return current
        time.sleep(0.01)
    raise AssertionError(f"article {article_id} never reached {state}")


def test_serial_dispatcher_publishes_a_complete_ready_article(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    dispatcher = SerialProcessingDispatcher(fake_processor)
    runtime = Runtime(settings, dispatcher=dispatcher)
    dispatcher.bind(runtime)
    try:
        created = runtime.submit_markdown(
            "# A listening test\n\nOne two three.\n\nFour five.",
            source_url="https://example.test/listening",
        )
        article_id = created["article"]["id"]
        ready = wait_for_state(runtime, article_id, "ready")

        assert ready["article"]["status"] == "ready"
        assert ready["article"]["audio_url"] == f"/api/articles/{article_id}/audio"
        assert ready["article"]["timings_url"] == f"/api/articles/{article_id}/timings"
        assert ready["article"]["production_seconds"] >= 0
        assert ready["article"]["telemetry"]["worker"] == "FakeNarrationWorker"

        directory = runtime.article_path(article_id)
        assert (directory / "document.json").is_file()
        assert (directory / "speech.json").is_file()
        assert (directory / "audio.wav").is_file()
        timings = json.loads((directory / "timings.json").read_text())
        assert [word["text"] for word in timings["words"]][:3] == ["A", "listening", "test"]
        assert all(
            left["start"] <= right["start"]
            for left, right in zip(timings["words"], timings["words"][1:])
        )
    finally:
        dispatcher.close()
        runtime.close()


def test_dispatcher_resumes_persisted_queued_jobs_when_server_starts(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    first = Runtime(settings)
    article_id = first.submit_markdown("# Queued\n\nProcess me later.")["article"]["id"]
    first.close()

    dispatcher = SerialProcessingDispatcher(fake_processor)
    restarted = Runtime(settings, dispatcher=dispatcher)
    dispatcher.bind(restarted)
    try:
        dispatcher.resume_pending()
        assert wait_for_state(restarted, article_id, "ready")["job"]["state"] == "ready"
    finally:
        dispatcher.close()
        restarted.close()


def test_cli_submission_uses_an_already_running_processing_server(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(home=tmp_path / "home")
    dispatcher = SerialProcessingDispatcher(fake_processor)
    runtime = Runtime(settings, dispatcher=dispatcher)
    dispatcher.bind(runtime)
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    source = tmp_path / "cli.md"
    source.write_text("# CLI bridge\n\nThis must leave the queue.")
    monkeypatch.setenv("LISTEN_READ_PORT", str(server.server_port))
    output: list[str] = []
    try:
        code = main(
            ["--home", str(settings.home), "--json", "add", "--markdown", str(source)],
            stdout=output.append,
        )
        created = json.loads("".join(output))

        assert code == 0
        assert wait_for_state(runtime, created["article"]["id"], "ready")["job"]["state"] == "ready"
    finally:
        server.shutdown()
        server.server_close()
        dispatcher.close()
        runtime.close()
        thread.join(timeout=3)


def test_cancelling_an_active_job_prevents_late_publication(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingWorker:
        def run(self, request):
            yield WorkerEvent(request.job_id, 0, "worker_started", {})
            started.set()
            release.wait(timeout=3)
            chunk = request.chunks[0]
            yield WorkerEvent(
                request.job_id,
                1,
                "chunk_completed",
                {"chunk_id": chunk.id, "timings": []},
            )

    def processor(_article_id: str) -> ArticleProcessor:
        return ArticleProcessor(
            worker=BlockingWorker(),
            model_revision="test-tts-revision",
            aligner_revision="test-aligner-revision",
        )

    settings = Settings(home=tmp_path / "home")
    dispatcher = SerialProcessingDispatcher(processor)
    runtime = Runtime(settings, dispatcher=dispatcher)
    dispatcher.bind(runtime)
    try:
        article_id = runtime.submit_markdown("# Cancel me\n\nStop this job.")["article"]["id"]
        assert started.wait(timeout=3)
        assert runtime.cancel(article_id)["job"]["state"] == "cancelled"
        release.set()
        time.sleep(0.05)

        current = runtime.get_article(article_id)
        assert current["job"]["state"] == "cancelled"
        assert not (runtime.article_path(article_id) / "audio.wav").exists()
    finally:
        release.set()
        dispatcher.close()
        runtime.close()


def test_prepared_document_policy_survives_runtime_processing(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    dispatcher = SerialProcessingDispatcher(fake_processor)
    runtime = Runtime(settings, dispatcher=dispatcher)
    dispatcher.bind(runtime)
    prepared = DocumentPipeline().prepare(
        acquire_markdown("# Prepared\n\nSee ![system](figure.png)."),
        ScientificPolicy(figure_descriptions={"system": "A careful spoken description."}),
    )
    try:
        article_id = runtime.submit_markdown(
            prepared.display.markdown,
            prepared_document=prepared.to_dict(),
        )["article"]["id"]
        wait_for_state(runtime, article_id, "ready")

        published = json.loads(runtime.artifact_path(article_id, "document.json").read_text())
        assert published["speech"]["policy"]["figure_descriptions"] == {
            "system": "A careful spoken description."
        }
        assert "careful spoken description" in published["speech"]["text"]
    finally:
        dispatcher.close()
        runtime.close()


def test_trashing_an_active_job_waits_until_the_worker_releases_files(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingWorker:
        def run(self, request):
            yield WorkerEvent(request.job_id, 0, "worker_started", {})
            started.set()
            release.wait(timeout=3)
            chunk = request.chunks[0]
            yield WorkerEvent(request.job_id, 1, "chunk_completed", {"chunk_id": chunk.id, "timings": []})

    def processor(_article_id: str) -> ArticleProcessor:
        return ArticleProcessor(
            worker=BlockingWorker(),
            model_revision="test-tts-revision",
            aligner_revision="test-aligner-revision",
        )

    settings = Settings(home=tmp_path / "home")
    dispatcher = SerialProcessingDispatcher(processor)
    runtime = Runtime(settings, dispatcher=dispatcher)
    dispatcher.bind(runtime)
    result: list[dict] = []
    try:
        article_id = runtime.submit_markdown("# Trash me\n\nStop safely.")["article"]["id"]
        assert started.wait(timeout=3)
        trash_thread = threading.Thread(target=lambda: result.append(runtime.trash(article_id)))
        trash_thread.start()
        deadline = time.monotonic() + 3
        while runtime.get_article(article_id)["job"]["state"] != "cancelled" and time.monotonic() < deadline:
            time.sleep(0.01)
        release.set()
        trash_thread.join(timeout=3)

        assert result[0]["article"]["status"] == "trashed"
        assert not (settings.home / "articles" / article_id).exists()
        assert (settings.home / "trash" / article_id).is_dir()
    finally:
        release.set()
        dispatcher.close()
        runtime.close()


def test_restoring_a_cancelled_trashed_article_requeues_it(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    try:
        article_id = runtime.submit_markdown("# Restore me\n\nContinue later.")["article"]["id"]

        assert runtime.trash(article_id)["job"]["state"] == "cancelled"
        restored = runtime.restore(article_id)

        assert restored["article"]["status"] == "processing"
        assert restored["job"]["state"] == "queued"
    finally:
        runtime.close()


def test_dispatcher_close_cancels_an_active_blocked_worker(tmp_path: Path) -> None:
    started = threading.Event()
    released = threading.Event()

    class CancellableWorker:
        def run(self, request):
            started.set()
            released.wait(timeout=30)
            yield WorkerEvent(request.job_id, 0, "worker_failed", {"message": "cancelled"})

        def cancel(self) -> None:
            released.set()

    def processor(_article_id: str) -> ArticleProcessor:
        return ArticleProcessor(
            worker=CancellableWorker(),
            model_revision="test-tts-revision",
            aligner_revision="test-aligner-revision",
        )

    dispatcher = SerialProcessingDispatcher(processor)
    runtime = Runtime(Settings(home=tmp_path / "home"), dispatcher=dispatcher)
    dispatcher.bind(runtime)
    runtime.submit_markdown("# Shutdown\n\nRelease the worker.")
    assert started.wait(timeout=3)

    began = time.monotonic()
    dispatcher.close()

    assert time.monotonic() - began < 3
    runtime.close()
