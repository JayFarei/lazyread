"""Narration worker process contracts and adapters."""

from .protocol import (
    FakeNarrationWorker,
    NarrationChunk,
    NarrationRequest,
    NarrationWord,
    WorkerEvent,
    run_jsonl_worker,
)
from .cache import chunk_cache_key
from .validation import (
    NarrationTiming,
    TimingBounds,
    TimingIssue,
    TimingValidationReport,
    repair_timings,
    validate_timings,
)
from .mlx_adapter import MlxTemplateWorkerAdapter

__all__ = [
    "FakeNarrationWorker",
    "NarrationChunk",
    "NarrationRequest",
    "NarrationWord",
    "WorkerEvent",
    "run_jsonl_worker",
    "chunk_cache_key",
    "NarrationTiming",
    "TimingBounds",
    "TimingIssue",
    "TimingValidationReport",
    "repair_timings",
    "validate_timings",
    "MlxTemplateWorkerAdapter",
]
