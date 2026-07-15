from __future__ import annotations

from pathlib import Path

import pytest

from lazyread.config import Settings
from lazyread.runtime import Runtime


def test_restart_marks_in_flight_jobs_interrupted_and_resumable(tmp_path: Path) -> None:
    settings = Settings(home=tmp_path / "home")
    first = Runtime(settings)
    article = first.submit_markdown("# Recovery\n\nA body.")["article"]
    first.transition_job(
        article["id"], "narrating", phase="narrating", completed=12, total=40
    )
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


def test_submission_notifies_an_injected_pipeline_without_loading_a_model(
    tmp_path: Path,
) -> None:
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


def test_restart_recovers_text_ready_jobs_instead_of_stranding_them(
    tmp_path: Path,
) -> None:
    settings = Settings(home=tmp_path / "home")
    first = Runtime(settings)
    article_id = first.submit_markdown("# Recovery\n\nText is already readable.")[
        "article"
    ]["id"]
    first.transition_job(
        article_id, "text_ready", phase="text_ready", completed=0, total=2
    )
    first.close()

    restarted = Runtime(settings)
    try:
        assert restarted.get_article(article_id)["job"]["state"] == "interrupted"
    finally:
        restarted.close()


def test_purge_keeps_the_catalog_entry_when_file_deletion_fails(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article_id = runtime.submit_markdown("# Keep catalog\n\nDeletion will fail.")[
        "article"
    ]["id"]
    runtime.trash(article_id)

    def cannot_remove(
        *_args: object, ignore_errors: bool = False, **_kwargs: object
    ) -> None:
        if ignore_errors:
            return
        raise PermissionError("article directory is not removable")

    monkeypatch.setattr("lazyread.runtime.shutil.rmtree", cannot_remove)
    try:
        with pytest.raises(PermissionError, match="not removable"):
            runtime.purge(article_id)

        assert runtime.get_article(article_id)["article"]["status"] == "trashed"
        assert (tmp_path / "home" / "trash" / article_id).is_dir()
    finally:
        runtime.close()
