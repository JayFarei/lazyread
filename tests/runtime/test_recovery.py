from __future__ import annotations

from pathlib import Path

from listen_read.config import Settings
from listen_read.runtime import Runtime


def test_restart_marks_in_flight_jobs_interrupted_and_resumable(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    first = Runtime(settings)
    article = first.submit_markdown("# Recovery\n\nA body.")["article"]
    first.transition_job(article["id"], "narrating", phase="narrating", completed=12, total=40)
    first.close()

    restarted = Runtime(settings)
    try:
        snapshot = restarted.get_article(article["id"])
        assert snapshot["job"]["state"] == "interrupted"
        assert snapshot["job"]["resumable"] is True
        assert snapshot["job"]["completed"] == 12
        assert snapshot["job"]["total"] == 40
    finally:
        restarted.close()


def test_submission_notifies_an_injected_pipeline_without_loading_a_model(tmp_path: Path) -> None:
    class FakeDispatcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Path]] = []

        def submit(self, article_id: str, home: Path) -> None:
            self.calls.append((article_id, home))

    fake = FakeDispatcher()
    runtime = Runtime(Settings(home=tmp_path / "home"), dispatcher=fake)
    try:
        created = runtime.submit_markdown("# Seam\n\nNo MLX here.")
        assert fake.calls == [(created["article"]["id"], tmp_path / "home")]
    finally:
        runtime.close()


def test_restart_recovers_text_ready_jobs_instead_of_stranding_them(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    first = Runtime(settings)
    article_id = first.submit_markdown("# Recovery\n\nText is already readable.")["article"]["id"]
    first.transition_job(article_id, "text_ready", phase="text_ready", completed=0, total=2)
    first.close()

    restarted = Runtime(settings)
    try:
        assert restarted.get_article(article_id)["job"]["state"] == "interrupted"
    finally:
        restarted.close()
