from __future__ import annotations

import json
from pathlib import Path
import wave

from lazyreader.pipeline import ArticleProcessor
from lazyreader.worker import FakeNarrationWorker, WorkerEvent


def test_article_processor_publishes_fake_ci_artifacts_and_runtime_transitions(
    tmp_path: Path,
) -> None:
    article = tmp_path / "articles" / "article-1"
    article.mkdir(parents=True)
    (article / "source.md").write_text("# Hello\n\nOne two three four.")
    transitions: list[tuple[str, dict[str, object]]] = []

    result = ArticleProcessor(
        worker=FakeNarrationWorker(seconds_per_word=0.1),
        voice="Aiden",
        settings={"style": "warm"},
        model_revision="fake-tts@1",
        aligner_revision="fake-aligner@1",
        mlx_audio_revision="fake-mlx-audio@1",
        max_chunk_words=2,
    ).process(
        "article-1",
        tmp_path,
        lambda state, payload: transitions.append((state, dict(payload))),
    )

    assert [state for state, _ in transitions] == [
        "canonicalizing",
        "text_ready",
        "narrating",
        "narrating",
        "narrating",
        "validating",
        "ready",
    ]
    assert result.audio_filename == "audio.wav"
    assert result.timings_filename == "timings.json"
    assert result.word_count == 5
    assert result.duration_seconds == 0.5
    assert result.model_revision == "fake-tts@1"
    assert result.aligner_revision == "fake-aligner@1"
    assert (article / "document.json").exists()
    assert (article / "speech.json").exists()
    manifest = json.loads((article / "timings.json").read_text())
    assert [word["text"] for word in manifest["words"]] == [
        "Hello",
        "One",
        "two",
        "three",
        "four",
    ]
    with wave.open(str(article / "audio.wav"), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 8_000
        assert audio.getnframes() == 4_000
    allowed_runtime_fields = {
        "phase",
        "completed",
        "total",
        "error",
        "resumable",
        "title",
    }
    assert all(set(payload) <= allowed_runtime_fields for _, payload in transitions)
    assert transitions[-1][1] == {"phase": "ready", "completed": 3, "total": 3}


def test_article_processor_can_acquire_url_when_source_file_is_empty(
    tmp_path: Path,
) -> None:
    article = tmp_path / "articles" / "article-url"
    article.mkdir(parents=True)
    (article / "source.md").write_text("")

    class Adapter:
        def acquire(self, url: str):
            from lazyreader.pipeline import acquire_markdown

            assert url == "https://example.com/story"
            return acquire_markdown("# From URL\n\nFetched.", source_url=url)

    result = ArticleProcessor(
        worker=FakeNarrationWorker(),
        model_revision="fake-tts@1",
        aligner_revision="fake-aligner@1",
        mlx_audio_revision="fake-mlx-audio@1",
        source_adapter=Adapter(),
    ).process(
        "article-url",
        tmp_path,
        lambda _state, _payload: None,
        source_url="https://example.com/story",
    )

    assert result.word_count == 3
    assert (article / "source.md").read_text() == "# From URL\n\nFetched."


def test_article_processor_does_not_publish_unvalidated_worker_output(
    tmp_path: Path,
) -> None:
    article = tmp_path / "articles" / "unsafe"
    article.mkdir(parents=True)
    (article / "source.md").write_text("One word.")

    class UnsafeWorker:
        def run(self, request):
            yield WorkerEvent(
                request.job_id,
                0,
                "worker_completed",
                {"duration_seconds": 1.0, "word_count": 2},
            )

    from lazyreader.pipeline import ArticleProcessingError
    import pytest

    with pytest.raises(ArticleProcessingError, match="validation"):
        ArticleProcessor(
            worker=UnsafeWorker(),
            model_revision="fake-tts@1",
            aligner_revision="fake-aligner@1",
            mlx_audio_revision="fake-mlx-audio@1",
        ).process("unsafe", tmp_path, lambda _state, _payload: None)

    assert not (article / "audio.wav").exists()
    assert not (article / "timings.json").exists()
