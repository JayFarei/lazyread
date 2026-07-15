from __future__ import annotations

import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .runtime import Runtime


FALLBACK_SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Lazyreader</title></head>
<body data-article-id="{article_id}"><main id="app"><h1>Lazyreader</h1>
<p>The web application is loading.</p></main></body></html>"""


class RuntimeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], runtime: Runtime):
        self.runtime = runtime
        self.web_root = _find_web_root(runtime)
        super().__init__(address, RequestHandler)


class RequestHandler(BaseHTTPRequestHandler):
    server: RuntimeHTTPServer
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard_request():
            return
        parsed = urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        try:
            if parsed.path == "/api/health":
                self._json(200, {"status": "ok", "version": __version__})
            elif parsed.path == "/api/articles":
                include_trashed = parse_qs(parsed.query).get("include_trashed") == ["1"]
                self._json(
                    200,
                    {
                        "articles": self.server.runtime.list_articles(
                            include_trashed=include_trashed
                        )
                    },
                )
            elif parsed.path == "/api/storage":
                self._json(200, {"storage": self.server.runtime.storage()})
            elif len(parts) == 3 and parts[:2] == ["api", "articles"]:
                self._json(200, self.server.runtime.get_article(parts[2]))
            elif (
                len(parts) == 4
                and parts[:2] == ["api", "articles"]
                and parts[3] == "timings"
            ):
                self._timings(parts[2])
            elif (
                len(parts) == 4
                and parts[:2] == ["api", "articles"]
                and parts[3] == "audio"
            ):
                self._audio(parts[2])
            elif (
                len(parts) == 4
                and parts[:2] == ["api", "articles"]
                and parts[3] == "events"
            ):
                self._events(parts[2], parse_qs(parsed.query))
            elif parsed.path.startswith("/assets/"):
                self._static(parsed.path.removeprefix("/"))
            elif parsed.path in {"/", "/library", "/settings/storage"} or (
                len(parts) == 2 and parts[0] == "read"
            ):
                article_id = parts[1] if len(parts) == 2 and parts[0] == "read" else ""
                if article_id:
                    self.server.runtime.get_article(article_id)
                self._shell(article_id)
            else:
                self._json(404, {"error": "not_found"})
        except KeyError as error:
            self._json(
                404, {"error": "article_not_found", "article_id": str(error.args[0])}
            )
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": "invalid_request", "message": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard_request(write=True):
            return
        parsed = urlsplit(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        try:
            body = self._body()
            if parsed.path == "/api/articles":
                markdown = body.get("markdown", "")
                source_url = body.get("source_url")
                if not markdown and not source_url:
                    raise ValueError("markdown or source_url is required")
                if markdown:
                    created = self.server.runtime.submit_markdown(
                        markdown,
                        title=body.get("title"),
                        source_url=source_url,
                        prepared_document=body.get("document"),
                    )
                else:
                    created = self.server.runtime.submit_source(
                        source_url, title=body.get("title")
                    )
                self._json(201, created)
            elif len(parts) == 4 and parts[:2] == ["api", "articles"]:
                action = parts[3]
                if action == "trash":
                    result = self.server.runtime.trash(parts[2])
                elif action == "restore":
                    result = self.server.runtime.restore(parts[2])
                elif action == "retry":
                    result = self.server.runtime.retry(parts[2])
                elif action == "cancel":
                    result = self.server.runtime.cancel(parts[2])
                elif action == "purge":
                    self.server.runtime.purge(parts[2])
                    self._json(200, {"purged": parts[2]})
                    return
                else:
                    self._json(404, {"error": "not_found"})
                    return
                self._json(200, result)
            else:
                self._json(404, {"error": "not_found"})
        except KeyError as error:
            self._json(
                404, {"error": "article_not_found", "article_id": str(error.args[0])}
            )
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": "invalid_request", "message": str(error)})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._guard_request(write=True):
            return
        parts = [part for part in urlsplit(self.path).path.split("/") if part]
        try:
            if len(parts) == 3 and parts[:2] == ["api", "articles"]:
                self.server.runtime.purge(parts[2])
                self._json(200, {"purged": parts[2]})
            else:
                self._json(404, {"error": "not_found"})
        except KeyError as error:
            self._json(
                404, {"error": "article_not_found", "article_id": str(error.args[0])}
            )
        except ValueError as error:
            self._json(409, {"error": "conflict", "message": str(error)})

    def do_PUT(self) -> None:  # noqa: N802
        if not self._guard_request(write=True):
            return
        parts = [part for part in urlsplit(self.path).path.split("/") if part]
        try:
            if (
                len(parts) == 4
                and parts[:2] == ["api", "articles"]
                and parts[3] == "highlights"
            ):
                body = self._body()
                highlights = body.get("highlights")
                if not isinstance(highlights, list):
                    raise ValueError("highlights must be an array")
                self._json(
                    200,
                    {
                        "highlights": self.server.runtime.replace_highlights(
                            parts[2], highlights
                        )
                    },
                )
            else:
                self._json(404, {"error": "not_found"})
        except KeyError as error:
            self._json(
                404, {"error": "article_not_found", "article_id": str(error.args[0])}
            )
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": "invalid_request", "message": str(error)})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 10 * 1024 * 1024:
            raise ValueError("request body exceeds 10 MiB")
        return json.loads(self.rfile.read(length) or b"{}")

    def _guard_request(self, *, write: bool = False) -> bool:
        host = urlsplit(f"//{self.headers.get('Host', '')}").hostname or ""
        trusted_host = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(
            ".ts.net"
        )
        if not trusted_host:
            self._json(421, {"error": "untrusted_host"})
            return False
        origin = self.headers.get("Origin")
        origin_host = urlsplit(origin).hostname if origin else None
        if self.headers.get("Sec-Fetch-Site") == "cross-site" or (
            origin_host is not None and origin_host != host
        ):
            self._json(403, {"error": "cross_origin_request_blocked"})
            return False
        if write and not self.headers.get("Content-Type", "").lower().startswith(
            "application/json"
        ):
            self._json(415, {"error": "application_json_required"})
            return False
        return True

    def _timings(self, article_id: str) -> None:
        path = self.server.runtime.artifact_path(article_id, "timings.json")
        if not path.is_file():
            self._json(404, {"error": "timings_not_found"})
            return
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["audio"] = f"/api/articles/{article_id}/audio"
        audio = self.server.runtime.audio_path(article_id)
        if audio.is_file():
            manifest["bytes"] = audio.stat().st_size
        self._json(200, manifest)

    def _audio(self, article_id: str) -> None:
        path = self.server.runtime.audio_path(article_id)
        if not path.is_file():
            self._json(404, {"error": "audio_not_found"})
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        requested = self.headers.get("Range")
        if requested:
            try:
                unit, bounds = requested.strip().split("=", 1)
                if unit != "bytes" or "," in bounds:
                    raise ValueError
                first, last = bounds.split("-", 1)
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                else:
                    suffix = int(last)
                    start = max(0, size - suffix)
                if start < 0 or start >= size or end < start:
                    raise ValueError
                status = HTTPStatus.PARTIAL_CONTENT
            except (ValueError, TypeError):
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        length = end - start + 1
        self.send_response(status)
        self.send_header(
            "Content-Type",
            mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=31536000, immutable")
        self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            remaining = length
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _events(self, article_id: str, query: dict[str, list[str]]) -> None:
        snapshot = self.server.runtime.snapshot(article_id)
        cursor = int(
            self.headers.get(
                "Last-Event-ID",
                query.get("last_event_id", query.get("since", ["0"]))[0],
            )
        )
        once = query.get("once") == ["1"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self._sse(snapshot["cursor"], "snapshot", snapshot)
        cursor = snapshot["cursor"]
        if once:
            return
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            events = self.server.runtime.events_after(article_id, cursor)
            for event in events:
                cursor = event["id"]
                if event["event"] == "job":
                    self._sse(
                        cursor, "progress", self.server.runtime.snapshot(article_id)
                    )
                else:
                    self._sse(cursor, event["event"], event["data"])
            if events:
                deadline = time.monotonic() + 25
            time.sleep(0.25)
        self.wfile.write(b": reconnect\n\n")
        self.wfile.flush()

    def _sse(self, sequence: int, kind: str, data: dict) -> None:
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        self.wfile.write(f"id: {sequence}\nevent: {kind}\ndata: {encoded}\n\n".encode())
        self.wfile.flush()

    def _shell(self, article_id: str) -> None:
        root = self.server.web_root
        if root and (root / "index.html").exists():
            html = (root / "index.html").read_text(encoding="utf-8")
            html = html.replace("<body", f'<body data-article-id="{article_id}"', 1)
        else:
            html = FALLBACK_SHELL.format(article_id=article_id)
        self._bytes(200, html.encode(), "text/html; charset=utf-8")

    def _static(self, relative: str) -> None:
        root = self.server.web_root
        if root is None:
            self._json(404, {"error": "asset_not_found"})
            return
        requested = (root / relative).resolve()
        if root.resolve() not in requested.parents or not requested.is_file():
            self._json(404, {"error": "asset_not_found"})
            return
        content_type = (
            mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        )
        self._bytes(200, requested.read_bytes(), content_type)

    def _json(self, status: int, data: dict) -> None:
        self._bytes(
            status,
            json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(),
            "application/json",
        )

    def _bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Cache-Control", "no-store" if "json" in content_type else "no-cache"
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
            "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return None


def _find_web_root(runtime: Runtime) -> Path | None:
    candidates = [runtime.settings.web_dir]
    package_web = Path(__file__).parent / "web"
    candidates.extend((package_web, Path.cwd() / "web" / "dist"))
    return next(
        (path for path in candidates if path and (path / "index.html").is_file()), None
    )


def create_server(runtime: Runtime, *, host: str, port: int) -> RuntimeHTTPServer:
    return RuntimeHTTPServer((host, port), runtime)
