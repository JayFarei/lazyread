from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from lazyreader.config import Settings
from lazyreader.runtime import Runtime
from lazyreader.server import create_server


def request(
    base: str, path: str, *, method: str = "GET", body: dict | None = None
) -> tuple[int, dict, dict]:
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        base + path,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(req, timeout=3)
    except urllib.error.HTTPError as error:
        response = error
    return response.status, dict(response.headers.items()), json.loads(response.read())


def test_http_api_exposes_stable_article_routes_and_lifecycle(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, _, created = request(
            base,
            "/api/articles",
            method="POST",
            body={
                "markdown": "# HTTP paper\n\nA body.",
                "source_url": "https://example.test/paper",
            },
        )
        article_id = created["article"]["id"]

        assert status == 201
        assert created["article"]["route"] == f"/read/{article_id}"
        assert request(base, "/api/articles")[2]["articles"][0]["id"] == article_id
        assert (
            request(base, f"/api/articles/{article_id}")[2]["article"]["source_url"]
            == "https://example.test/paper"
        )
        assert (
            request(base, f"/api/articles/{article_id}/trash", method="POST")[2][
                "article"
            ]["status"]
            == "trashed"
        )
        assert (
            request(base, f"/api/articles/{article_id}/restore", method="POST")[2][
                "article"
            ]["status"]
            == "processing"
        )
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_sse_starts_with_persisted_snapshot_and_resume_cursor(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article = runtime.submit_markdown("# Events\n\nA body.")["article"]
    runtime.transition_job(
        article["id"], "text_ready", phase="canonicalizing", completed=1, total=4
    )
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/articles/{article['id']}/events?once=1"
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            stream = response.read().decode()

        assert response.headers["Content-Type"].startswith("text/event-stream")
        assert "event: snapshot" in stream
        assert '"state":"text_ready"' in stream
        assert '"completed":1' in stream
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_title_resolution_is_emitted_only_when_it_replaces_a_url_placeholder(
    tmp_path: Path,
) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    try:
        source_url = "https://example.test/article"
        acquired_id = runtime.submit_source(source_url)["article"]["id"]
        explicit_id = runtime.submit_source(source_url, title="Keep this title")[
            "article"
        ]["id"]

        runtime.transition_job(acquired_id, "text_ready", title="Acquired title")
        runtime.transition_job(explicit_id, "text_ready", title="Fetched title")

        acquired_events = runtime.events_after(acquired_id, 0)
        explicit_events = runtime.events_after(explicit_id, 0)
        assert acquired_events[-1]["data"]["title"] == "Acquired title"
        assert "title" not in explicit_events[-1]["data"]
        assert runtime.get_article(explicit_id)["article"]["title"] == "Keep this title"
    finally:
        runtime.close()


def test_snapshot_cannot_pair_stale_state_with_a_newer_event_cursor(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article_id = runtime.submit_markdown("# Snapshot race\n\nA body.")["article"]["id"]
    snapshot_started = threading.Event()
    release_snapshot = threading.Event()
    transition_finished = threading.Event()
    snapshots: list[dict] = []
    original_get_article = runtime.get_article

    def paused_get_article(requested_id: str) -> dict:
        data = original_get_article(requested_id)
        if not snapshot_started.is_set():
            snapshot_started.set()
            release_snapshot.wait(timeout=3)
        return data

    monkeypatch.setattr(runtime, "get_article", paused_get_article)
    snapshot_thread = threading.Thread(
        target=lambda: snapshots.append(runtime.snapshot(article_id))
    )

    def transition() -> None:
        runtime.transition_job(article_id, "text_ready", phase="text_ready")
        transition_finished.set()

    transition_thread = threading.Thread(target=transition)
    try:
        snapshot_thread.start()
        assert snapshot_started.wait(timeout=3)
        transition_thread.start()

        assert not transition_finished.wait(timeout=0.1)
        release_snapshot.set()
        snapshot_thread.join(timeout=3)
        transition_thread.join(timeout=3)

        snapshot = snapshots[0]
        assert snapshot["job"]["state"] == "queued"
        assert any(
            event["data"].get("state") == "text_ready"
            for event in runtime.events_after(article_id, snapshot["cursor"])
        )
    finally:
        release_snapshot.set()
        snapshot_thread.join(timeout=3)
        transition_thread.join(timeout=3)
        runtime.close()


def test_read_route_uses_embedded_shell_hook(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article = runtime.submit_markdown("# Route\n\nA body.")["article"]
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/read/{article['id']}", timeout=3
        )
        html = response.read().decode()
        assert response.status == 200
        assert "Lazyreader" in html
        assert f'data-article-id="{article["id"]}"' in html
        assert "fonts.googleapis.com" not in html
        assert "fonts.gstatic.com" not in html
        assert "font-src 'self'" in response.headers["Content-Security-Policy"]
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_ready_artifacts_are_served_through_safe_revision_stable_urls_with_ranges(
    tmp_path: Path,
) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article = runtime.submit_markdown("# Audio\n\nOne two.")["article"]
    article_id = article["id"]
    artifacts = runtime.article_path(article_id)
    (artifacts / "audio.flac").write_bytes(b"0123456789")
    (artifacts / "timings.json").write_text(
        json.dumps(
            {
                "audio": "old.flac",
                "duration": 1.2,
                "words": [{"index": 0, "text": "One", "start": 0, "end": 0.5}],
            }
        ),
        encoding="utf-8",
    )
    runtime.transition_job(article_id, "ready")
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        detail = request(base, f"/api/articles/{article_id}")[2]["article"]
        assert detail["audio_url"] == f"/api/articles/{article_id}/audio"
        assert detail["timings_url"] == f"/api/articles/{article_id}/timings"

        timings = request(base, f"/api/articles/{article_id}/timings")[2]
        assert timings["audio"] == f"/api/articles/{article_id}/audio"
        assert timings["bytes"] == 10

        ranged = urllib.request.Request(
            base + f"/api/articles/{article_id}/audio", headers={"Range": "bytes=2-5"}
        )
        with urllib.request.urlopen(ranged, timeout=3) as response:
            assert response.status == 206
            assert response.headers["Accept-Ranges"] == "bytes"
            assert response.headers["Content-Range"] == "bytes 2-5/10"
            assert response.read() == b"2345"
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_http_retry_cancel_and_post_purge_actions(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article_id = runtime.submit_markdown("# Actions\n\nA body.")["article"]["id"]
    runtime.transition_job(article_id, "failed", error="temporary")
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        retried = request(base, f"/api/articles/{article_id}/retry", method="POST")[2]
        assert retried["job"]["state"] == "queued"
        assert retried["job"]["error"] is None
        cancelled = request(base, f"/api/articles/{article_id}/cancel", method="POST")[
            2
        ]
        assert cancelled["job"]["state"] == "cancelled"
        request(base, f"/api/articles/{article_id}/trash", method="POST")
        assert request(base, f"/api/articles/{article_id}/purge", method="POST")[2] == {
            "purged": article_id
        }
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_highlights_persist_in_the_article_library(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article_id = runtime.submit_markdown("# Notes\n\nKeep this sentence.")["article"][
        "id"
    ]
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        saved = request(
            base,
            f"/api/articles/{article_id}/highlights",
            method="PUT",
            body={
                "highlights": [
                    {
                        "id": "0-3",
                        "text": "Keep this sentence.",
                        "startIndex": 0,
                        "endIndex": 3,
                    }
                ]
            },
        )[2]

        assert saved["highlights"][0]["text"] == "Keep this sentence."
        assert (
            request(base, f"/api/articles/{article_id}")[2]["article"]["highlights"][0][
                "id"
            ]
            == "0-3"
        )
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_http_boundary_blocks_dns_rebinding_cross_site_writes_and_plain_forms(
    tmp_path: Path,
) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        bad_host = urllib.request.Request(
            base + "/api/health", headers={"Host": "evil.example"}
        )
        with pytest.raises(urllib.error.HTTPError) as host_error:
            urllib.request.urlopen(bad_host)
        assert host_error.value.code == 421

        hostile = urllib.request.Request(
            base + "/api/articles",
            data=b'{"markdown":"# Hostile"}',
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://evil.example",
            },
        )
        with pytest.raises(urllib.error.HTTPError) as origin_error:
            urllib.request.urlopen(hostile)
        assert origin_error.value.code == 403

        plain = urllib.request.Request(
            base + "/api/articles",
            data=b'{"markdown":"# Form"}',
            method="POST",
            headers={"Content-Type": "text/plain"},
        )
        with pytest.raises(urllib.error.HTTPError) as type_error:
            urllib.request.urlopen(plain)
        assert type_error.value.code == 415
        assert runtime.list_articles() == []
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)
