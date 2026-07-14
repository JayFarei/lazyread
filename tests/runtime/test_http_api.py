from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from listen_read.config import Settings
from listen_read.runtime import Runtime
from listen_read.server import create_server


def request(base: str, path: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict, dict]:
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
            body={"markdown": "# HTTP paper\n\nA body.", "source_url": "https://example.test/paper"},
        )
        article_id = created["article"]["id"]

        assert status == 201
        assert created["article"]["route"] == f"/read/{article_id}"
        assert request(base, "/api/articles")[2]["articles"][0]["id"] == article_id
        assert request(base, f"/api/articles/{article_id}")[2]["article"]["source_url"] == "https://example.test/paper"
        assert request(base, f"/api/articles/{article_id}/trash", method="POST")[2]["article"]["status"] == "trashed"
        assert request(base, f"/api/articles/{article_id}/restore", method="POST")[2]["article"]["status"] == "processing"
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_sse_starts_with_persisted_snapshot_and_resume_cursor(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article = runtime.submit_markdown("# Events\n\nA body.")["article"]
    runtime.transition_job(article["id"], "text_ready", phase="canonicalizing", completed=1, total=4)
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
        assert "Listen Read" in html
        assert f'data-article-id="{article["id"]}"' in html
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_ready_artifacts_are_served_through_safe_revision_stable_urls_with_ranges(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article = runtime.submit_markdown("# Audio\n\nOne two.")["article"]
    article_id = article["id"]
    artifacts = runtime.article_path(article_id)
    (artifacts / "audio.flac").write_bytes(b"0123456789")
    (artifacts / "timings.json").write_text(
        json.dumps({"audio": "old.flac", "duration": 1.2, "words": [{"index": 0, "text": "One", "start": 0, "end": 0.5}]}),
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
        cancelled = request(base, f"/api/articles/{article_id}/cancel", method="POST")[2]
        assert cancelled["job"]["state"] == "cancelled"
        request(base, f"/api/articles/{article_id}/trash", method="POST")
        assert request(base, f"/api/articles/{article_id}/purge", method="POST")[2] == {"purged": article_id}
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_highlights_persist_in_the_article_library(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    article_id = runtime.submit_markdown("# Notes\n\nKeep this sentence.")["article"]["id"]
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        saved = request(
            base,
            f"/api/articles/{article_id}/highlights",
            method="PUT",
            body={"highlights": [{"id": "0-3", "text": "Keep this sentence.", "startIndex": 0, "endIndex": 3}]},
        )[2]

        assert saved["highlights"][0]["text"] == "Keep this sentence."
        assert request(base, f"/api/articles/{article_id}")[2]["article"]["highlights"][0]["id"] == "0-3"
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=3)


def test_http_boundary_blocks_dns_rebinding_cross_site_writes_and_plain_forms(tmp_path: Path) -> None:
    runtime = Runtime(Settings(home=tmp_path / "home"))
    server = create_server(runtime, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        bad_host = urllib.request.Request(base + "/api/health", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as host_error:
            urllib.request.urlopen(bad_host)
        assert host_error.value.code == 421

        hostile = urllib.request.Request(
            base + "/api/articles",
            data=b'{"markdown":"# Hostile"}',
            method="POST",
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
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
