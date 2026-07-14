from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings
from .database import connect
from .dispatcher import DeferredDispatcher, PipelineDispatcher


ACTIVE_STATES = {
    "acquiring",
    "canonicalizing",
    "preparing",
    "narrating",
    "aligning",
    "assembling",
    "validating",
    "preloading_available",
}
VALID_STATES = {
    "queued",
    *ACTIVE_STATES,
    "text_ready",
    "ready",
    "interrupted",
    "failed",
    "cancelling",
    "cancelled",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def title_from_markdown(markdown: str) -> str:
    heading = re.search(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
    return heading.group(1).strip() if heading else "Untitled article"


def _directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


class Runtime:
    """Public application service for the durable listening library."""

    def __init__(self, settings: Settings, dispatcher: PipelineDispatcher | None = None):
        self.settings = settings
        self.settings.ensure_directories()
        self._connection = connect(settings.home / "listen-read.sqlite")
        self._lock = threading.RLock()
        self._dispatcher = dispatcher or DeferredDispatcher()
        self._recover_interrupted_jobs()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _recover_interrupted_jobs(self) -> None:
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        stamp = now()
        with self._lock, self._connection:
            rows = self._connection.execute(
                f"SELECT article_id FROM jobs WHERE state IN ({placeholders})", tuple(ACTIVE_STATES)
            ).fetchall()
            self._connection.execute(
                f"UPDATE jobs SET state='interrupted', resumable=1, updated_at=? "
                f"WHERE state IN ({placeholders})",
                (stamp, *ACTIVE_STATES),
            )
            for row in rows:
                self._append_event(row["article_id"], "job", {"state": "interrupted", "resumable": True})

    def submit_markdown(
        self,
        markdown: str,
        *,
        title: str | None = None,
        source_url: str | None = None,
        prepared_document: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        article_id = str(uuid.uuid4())
        stamp = now()
        article_dir = self.settings.home / "articles" / article_id
        temporary = self.settings.home / "articles" / f".{article_id}.tmp"
        temporary.mkdir(parents=True)
        try:
            (temporary / "source.md").write_text(markdown, encoding="utf-8")
            if prepared_document is not None:
                (temporary / "document.json").write_text(
                    json.dumps(prepared_document, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            os.replace(temporary, article_dir)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

        resolved_title = (title or title_from_markdown(markdown)).strip() or "Untitled article"
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    "INSERT INTO articles(id,title,source_url,status,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (article_id, resolved_title, source_url, "processing", stamp, stamp),
                )
                self._connection.execute(
                    "INSERT INTO jobs(article_id,state,phase,updated_at) VALUES(?,?,?,?)",
                    (article_id, "queued", "queued", stamp),
                )
                self._append_event(article_id, "article", {"status": "processing"})
                self._append_event(article_id, "job", {"state": "queued", "phase": "queued"})
        except BaseException:
            shutil.rmtree(article_dir, ignore_errors=True)
            raise

        self._dispatcher.submit(article_id, self.settings.home)
        return self.get_article(article_id)

    def submit_source(self, source_url: str, *, title: str | None = None) -> dict[str, Any]:
        label = title or source_url
        return self.submit_markdown("", title=label, source_url=source_url)

    def list_articles(self, *, include_trashed: bool = False) -> list[dict[str, Any]]:
        where = "" if include_trashed else "WHERE a.status != 'trashed'"
        with self._lock:
            rows = self._connection.execute(
                f"SELECT a.*,j.state,j.phase,j.completed,j.total,j.resumable,j.error,j.updated_at AS job_updated_at "
                f"FROM articles a JOIN jobs j ON j.article_id=a.id {where} "
                "ORDER BY a.created_at DESC"
            ).fetchall()
        return [self._decorate_artifacts(self._summary(row)) for row in rows]

    def get_article(self, article_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT a.*,j.state,j.phase,j.completed,j.total,j.resumable,j.error,j.updated_at AS job_updated_at "
                "FROM articles a JOIN jobs j ON j.article_id=a.id WHERE a.id=?",
                (article_id,),
            ).fetchone()
        if row is None:
            raise KeyError(article_id)
        location = self._article_directory(article_id, row["status"])
        source_path = location / "source.md"
        result = self._decorate_artifacts(self._summary(row))
        result["markdown"] = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        document_path = location / "document.json"
        if document_path.exists():
            result["document"] = json.loads(document_path.read_text(encoding="utf-8"))
        return {"article": result, "job": result["job"]}

    def article_path(self, article_id: str) -> Path:
        """Return the durable artifact directory after validating article identity."""
        with self._lock:
            row = self._connection.execute(
                "SELECT status FROM articles WHERE id=?", (article_id,)
            ).fetchone()
        if row is None:
            raise KeyError(article_id)
        return self._article_directory(article_id, row["status"])

    def artifact_path(self, article_id: str, name: str) -> Path:
        allowed = {"timings.json", "telemetry.json", "document.json", "speech.json"}
        if name not in allowed:
            raise ValueError(f"Unsupported article artifact: {name}")
        return self.article_path(article_id) / name

    def audio_path(self, article_id: str) -> Path:
        directory = self.article_path(article_id)
        timings = directory / "timings.json"
        candidates: list[str] = []
        if timings.is_file():
            try:
                declared = json.loads(timings.read_text(encoding="utf-8")).get("audio")
                if isinstance(declared, str):
                    candidates.append(declared)
            except (json.JSONDecodeError, OSError):
                pass
        candidates.extend(("audio.flac", "audio.wav"))
        for name in candidates:
            candidate = directory / name
            if (
                Path(name).name == name
                and candidate.suffix.lower() in {".flac", ".wav", ".mp3", ".m4a"}
                and candidate.is_file()
            ):
                return candidate
        return directory / "audio.flac"

    def transition_job(
        self,
        article_id: str,
        state: str,
        *,
        phase: str | None = None,
        completed: int | None = None,
        total: int | None = None,
        error: str | None = None,
        resumable: bool | None = None,
        completed_chunks: int | None = None,
        total_chunks: int | None = None,
        message: str | None = None,
        **_artifact_metadata: Any,
    ) -> dict[str, Any]:
        if state not in VALID_STATES:
            raise ValueError(f"Unknown job state: {state}")
        completed = completed if completed is not None else completed_chunks
        total = total if total is not None else total_chunks
        error = error if error is not None else message
        stamp = now()
        updates = ["state=?", "updated_at=?"]
        values: list[Any] = [state, stamp]
        for column, value in (("phase", phase), ("completed", completed), ("total", total), ("error", error)):
            if value is not None:
                updates.append(f"{column}=?")
                values.append(value)
        if resumable is not None:
            updates.append("resumable=?")
            values.append(int(resumable))
        elif state in {"ready", "failed", "cancelled"}:
            updates.append("resumable=0")
        values.append(article_id)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"UPDATE jobs SET {','.join(updates)} WHERE article_id=?", values
            )
            if cursor.rowcount == 0:
                raise KeyError(article_id)
            article_status = "ready" if state == "ready" else "failed" if state == "failed" else "processing"
            self._connection.execute(
                "UPDATE articles SET status=?,updated_at=? WHERE id=? AND status!='trashed'",
                (article_status, stamp, article_id),
            )
            event = {"state": state, "phase": phase or state}
            if completed is not None:
                event["completed"] = completed
            if total is not None:
                event["total"] = total
            if error is not None:
                event["error"] = error
            self._append_event(article_id, "job", event)
        return self.get_article(article_id)

    def trash(self, article_id: str) -> dict[str, Any]:
        return self._move(article_id, trash=True)

    def restore(self, article_id: str) -> dict[str, Any]:
        return self._move(article_id, trash=False)

    def _move(self, article_id: str, *, trash: bool) -> dict[str, Any]:
        current = self.get_article(article_id)
        status = current["article"]["status"]
        if trash and status == "trashed":
            return current
        if not trash and status != "trashed":
            return current
        source = self._article_directory(article_id, status)
        destination = self.settings.home / ("trash" if trash else "articles") / article_id
        if source.exists():
            os.replace(source, destination)
        stamp = now()
        next_status = "trashed" if trash else self._status_for_job(current["job"]["state"])
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE articles SET status=?,trashed_at=?,updated_at=? WHERE id=?",
                (next_status, stamp if trash else None, stamp, article_id),
            )
            self._append_event(article_id, "article", {"status": next_status})
        return self.get_article(article_id)

    def purge(self, article_id: str) -> None:
        article = self.get_article(article_id)
        if article["article"]["status"] != "trashed":
            raise ValueError("Article must be trashed before it can be purged")
        shutil.rmtree(self.settings.home / "trash" / article_id, ignore_errors=True)
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM articles WHERE id=?", (article_id,))

    def retry(self, article_id: str) -> dict[str, Any]:
        current = self.get_article(article_id)
        if current["article"]["status"] == "trashed":
            raise ValueError("Restore the article before retrying it")
        if current["job"]["state"] not in {"failed", "interrupted", "cancelled"}:
            raise ValueError(f"Job cannot be retried from {current['job']['state']}")
        stamp = now()
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE jobs SET state='queued',phase='queued',resumable=0,error=NULL,updated_at=? WHERE article_id=?",
                (stamp, article_id),
            )
            self._connection.execute(
                "UPDATE articles SET status='processing',updated_at=? WHERE id=?", (stamp, article_id)
            )
            self._append_event(article_id, "job", {"state": "queued", "phase": "queued"})
        self._dispatcher.submit(article_id, self.settings.home)
        return self.get_article(article_id)

    def cancel(self, article_id: str) -> dict[str, Any]:
        current = self.get_article(article_id)
        if current["job"]["state"] in {"ready", "failed", "cancelled"}:
            raise ValueError(f"Job cannot be cancelled from {current['job']['state']}")
        return self.transition_job(article_id, "cancelled", phase="cancelled", resumable=False)

    def clear_cache(self, scope: str) -> dict[str, Any]:
        paths = {
            "chunks": self.settings.home / "cache" / "chunks",
            "models": self.settings.home / "cache" / "models",
        }
        if scope not in paths:
            raise ValueError("cache scope must be chunks or models")
        path = paths[scope]
        removed = _directory_bytes(path)
        shutil.rmtree(path, ignore_errors=False)
        path.mkdir(parents=True)
        return {"cleared": scope, "bytes_removed": removed}

    def storage(self) -> dict[str, dict[str, int]]:
        paths = {
            "articles": self.settings.home / "articles",
            "temporary_chunks": self.settings.home / "cache" / "chunks",
            "models": self.settings.home / "cache" / "models",
            "runtime": self.settings.home / "runtime",
            "trash": self.settings.home / "trash",
        }
        result = {name: {"bytes": _directory_bytes(path)} for name, path in paths.items()}
        result["total"] = {
            "bytes": sum(value["bytes"] for value in result.values())
            + _directory_bytes(self.settings.home / "listen-read.sqlite")
        }
        return result

    def snapshot(self, article_id: str) -> dict[str, Any]:
        data = self.get_article(article_id)
        data["cursor"] = self.latest_sequence(article_id)
        return data

    def events_after(self, article_id: str, sequence: int) -> list[dict[str, Any]]:
        self.get_article(article_id)
        with self._lock:
            rows = self._connection.execute(
                "SELECT sequence,kind,payload,created_at FROM events "
                "WHERE article_id=? AND sequence>? ORDER BY sequence",
                (article_id, sequence),
            ).fetchall()
        return [
            {
                "id": row["sequence"],
                "event": row["kind"],
                "data": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def latest_sequence(self, article_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence),0) AS sequence FROM events WHERE article_id=?", (article_id,)
            ).fetchone()
        return int(row["sequence"])

    def _append_event(self, article_id: str, kind: str, payload: dict[str, Any]) -> None:
        self._connection.execute(
            "INSERT INTO events(article_id,kind,payload,created_at) VALUES(?,?,?,?)",
            (article_id, kind, json.dumps(payload, separators=(",", ":")), now()),
        )

    def _article_directory(self, article_id: str, status: str) -> Path:
        return self.settings.home / ("trash" if status == "trashed" else "articles") / article_id

    def _decorate_artifacts(self, article: dict[str, Any]) -> dict[str, Any]:
        directory = self._article_directory(article["id"], article["status"])
        audio = self.audio_path(article["id"])
        timings = directory / "timings.json"
        if audio.is_file():
            article["audio_url"] = f"/api/articles/{article['id']}/audio"
            article["artifact_bytes"] = audio.stat().st_size
        if timings.is_file():
            article["timings_url"] = f"/api/articles/{article['id']}/timings"
            try:
                manifest = json.loads(timings.read_text(encoding="utf-8"))
                revision = manifest.get("revision") or manifest.get("audio_revision")
                if revision:
                    article["audio_revision"] = revision
                duration = manifest.get("duration") or manifest.get("duration_seconds")
                if duration is not None:
                    article["duration_seconds"] = duration
                words = manifest.get("words") or manifest.get("timings")
                if isinstance(words, list):
                    article["word_count"] = len(words)
            except (json.JSONDecodeError, OSError):
                pass
        telemetry = directory / "telemetry.json"
        if telemetry.is_file():
            try:
                profile = json.loads(telemetry.read_text(encoding="utf-8"))
                article["telemetry"] = profile
                wall_seconds = profile.get("wall_seconds", profile.get("totalWallSeconds"))
                peak_memory = profile.get("peak_rss_bytes", profile.get("mlxPeakMemoryBytes"))
                if wall_seconds is not None:
                    article["production_seconds"] = wall_seconds
                if peak_memory is not None:
                    article["peak_memory_bytes"] = peak_memory
            except (json.JSONDecodeError, OSError):
                pass
        return article

    @staticmethod
    def _status_for_job(state: str) -> str:
        if state == "ready":
            return "ready"
        if state == "failed":
            return "failed"
        return "processing"

    @staticmethod
    def _summary(row: Any) -> dict[str, Any]:
        article_id = row["id"]
        return {
            "id": article_id,
            "title": row["title"],
            "source_url": row["source_url"],
            "status": row["status"],
            "route": f"/read/{article_id}",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "trashed_at": row["trashed_at"],
            "job": {
                "state": row["state"],
                "phase": row["phase"],
                "completed": row["completed"],
                "total": row["total"],
                "resumable": bool(row["resumable"]),
                "error": row["error"],
                "updated_at": row["job_updated_at"],
            },
        }
