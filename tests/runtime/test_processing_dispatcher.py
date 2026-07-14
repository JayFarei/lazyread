from __future__ import annotations

import json
import time
from pathlib import Path

from listen_read.config import Settings
from listen_read.dispatcher import SerialProcessingDispatcher
from listen_read.pipeline import ArticleProcessor
from listen_read.runtime import Runtime
from listen_read.worker import FakeNarrationWorker


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
