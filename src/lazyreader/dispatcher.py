from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from .pipeline import ArticleProcessor
    from .runtime import Runtime


class PipelineDispatcher(Protocol):
    """Injection seam between persistence and the document/narration pipeline."""

    def submit(self, article_id: str, home: Path) -> None: ...

    def cancel(self, article_id: str) -> None: ...

    def wait(self, article_id: str, timeout: float) -> bool: ...


class DeferredDispatcher:
    """The server/worker integration claims queued jobs outside this process."""

    def submit(self, article_id: str, home: Path) -> None:
        return None

    def cancel(self, article_id: str) -> None:
        return None

    def wait(self, article_id: str, timeout: float) -> bool:
        return True


ProcessorFactory = Callable[[str], "ArticleProcessor"]


class ProcessingCancelled(RuntimeError):
    """Cooperative cancellation crossed the persisted pipeline boundary."""


class SerialProcessingDispatcher:
    """Run the expensive article pipeline one job at a time.

    The queue is intentionally in-process and disposable: SQLite remains the
    source of truth, and ``resume_pending`` reconstructs work after a restart.
    The heavyweight model process is owned by each processor invocation, so it
    exits when the queue drains instead of retaining unified memory.
    """

    def __init__(self, processor_factory: ProcessorFactory) -> None:
        self._processor_factory = processor_factory
        self._runtime: Runtime | None = None
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._scheduled: set[str] = set()
        self._cancelled: set[str] = set()
        self._done: dict[str, threading.Event] = {}
        self._active_processors: dict[str, ArticleProcessor] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def bind(self, runtime: Runtime) -> None:
        if self._runtime is not None:
            raise RuntimeError("processing dispatcher is already bound")
        self._runtime = runtime
        self._thread = threading.Thread(
            target=self._run,
            name="lazyreader-processing",
            daemon=True,
        )
        self._thread.start()

    def submit(self, article_id: str, home: Path) -> None:
        del home
        with self._lock:
            self._cancelled.discard(article_id)
            if article_id in self._scheduled:
                return
            self._scheduled.add(article_id)
            self._done.setdefault(article_id, threading.Event()).clear()
            self._queue.put(article_id)

    def cancel(self, article_id: str) -> None:
        with self._lock:
            self._cancelled.add(article_id)
            processor = self._active_processors.get(article_id)
        if processor is not None:
            processor.cancel()

    def wait(self, article_id: str, timeout: float) -> bool:
        with self._lock:
            if article_id not in self._active_processors:
                return True
            event = self._done.get(article_id)
        return True if event is None else event.wait(timeout)

    def resume_pending(self) -> None:
        runtime = self._require_runtime()
        for article in runtime.list_articles():
            if article["job"]["state"] in {"queued", "interrupted"}:
                self.submit(article["id"], runtime.settings.home)

    def close(self) -> None:
        if self._thread is None:
            return
        with self._lock:
            self._cancelled.update(self._scheduled)
            active = list(self._active_processors.values())
        for processor in active:
            processor.cancel()
        self._queue.put(None)
        self._thread.join(timeout=180)
        if self._thread.is_alive():
            raise RuntimeError("narration worker did not stop within 180 seconds")
        self._thread = None

    def _require_runtime(self) -> Runtime:
        if self._runtime is None:
            raise RuntimeError("processing dispatcher must be bound before use")
        return self._runtime

    def _run(self) -> None:
        runtime = self._require_runtime()
        while True:
            article_id = self._queue.get()
            if article_id is None:
                self._queue.task_done()
                return
            processor: ArticleProcessor | None = None
            try:
                try:
                    current = runtime.get_article(article_id)
                except KeyError:
                    # A queued article can be purged before the worker claims it.
                    continue
                if current["article"]["status"] == "trashed" or current["job"][
                    "state"
                ] in {
                    "ready",
                    "cancelled",
                }:
                    continue
                source_url = current["article"].get("source_url")
                processor = self._processor_factory(article_id)
                with self._lock:
                    self._active_processors[article_id] = processor
                    cancelled = article_id in self._cancelled
                if cancelled:
                    processor.cancel()
                    raise ProcessingCancelled(article_id)
                processor.process(
                    article_id,
                    runtime.settings.home,
                    lambda state, payload: self._transition(
                        runtime, article_id, state, payload
                    ),
                    source_url=source_url,
                )
            except ProcessingCancelled:
                pass
            except Exception as error:  # the durable failed state is the boundary
                try:
                    current = runtime.get_article(article_id)
                    if current["job"]["state"] != "failed":
                        runtime.transition_job(
                            article_id,
                            "failed",
                            phase="failed",
                            error=f"{type(error).__name__}: {error}",
                            resumable=True,
                        )
                except KeyError:
                    pass
            finally:
                if processor is not None:
                    processor.cleanup()
                with self._lock:
                    self._active_processors.pop(article_id, None)
                    self._scheduled.discard(article_id)
                    self._done.setdefault(article_id, threading.Event()).set()
                self._queue.task_done()

    def _transition(
        self,
        runtime: Runtime,
        article_id: str,
        state: str,
        payload: dict,
    ) -> None:
        with self._lock:
            if article_id in self._cancelled:
                raise ProcessingCancelled(article_id)
            runtime.transition_job(article_id, state, **payload)
