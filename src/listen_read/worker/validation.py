from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .protocol import NarrationWord


@dataclass(frozen=True, slots=True)
class TimingBounds:
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Timing bounds must have a non-negative, positive range")


@dataclass(frozen=True, slots=True)
class NarrationTiming:
    word_id: str
    text: str
    start: float
    end: float
    chunk_id: str


@dataclass(frozen=True, slots=True)
class TimingIssue:
    code: str
    message: str
    word_id: str | None = None


@dataclass(frozen=True, slots=True)
class TimingValidationReport:
    issues: tuple[TimingIssue, ...]
    repair_stage: str | None
    reuse_cached_speech: bool

    @property
    def valid(self) -> bool:
        return not self.issues


def validate_timings(
    timings: Sequence[NarrationTiming],
    *,
    expected_words: Sequence[NarrationWord],
    audio_duration: float,
    chunk_bounds: Mapping[str, TimingBounds],
) -> TimingValidationReport:
    """Apply the publication timing gate and classify the cheapest repair."""

    issues: list[TimingIssue] = []
    identities_match = len(timings) == len(expected_words)
    if not identities_match:
        issues.append(
            TimingIssue(
                "word_count_mismatch",
                f"Expected {len(expected_words)} timings but received {len(timings)}.",
            )
        )

    for index, timing in enumerate(timings):
        if index < len(expected_words):
            expected = expected_words[index]
            if timing.word_id != expected.id or timing.text != expected.text:
                identities_match = False
                issues.append(
                    TimingIssue(
                        "word_identity_mismatch",
                        f"Timing {index} does not match the prepared speech word.",
                        timing.word_id,
                    )
                )
        if timing.start < 0 or timing.end > audio_duration:
            issues.append(
                TimingIssue(
                    "outside_audio_bounds",
                    "Word timing lies outside the assembled audio track.",
                    timing.word_id,
                )
            )
        if timing.end <= timing.start:
            issues.append(
                TimingIssue(
                    "non_positive_duration",
                    "Word timing must have positive duration.",
                    timing.word_id,
                )
            )
        if index and timing.start < timings[index - 1].start:
            issues.append(
                TimingIssue(
                    "non_monotonic_start",
                    "Word starts must be monotonic across the complete track.",
                    timing.word_id,
                )
            )
        bounds = chunk_bounds.get(timing.chunk_id)
        if bounds is None:
            issues.append(
                TimingIssue(
                    "unknown_chunk",
                    "Timing refers to a chunk without declared audio bounds.",
                    timing.word_id,
                )
            )
        elif timing.start < bounds.start or timing.end > bounds.end:
            issues.append(
                TimingIssue(
                    "outside_chunk_bounds",
                    "Word timing lies outside its synthesized chunk.",
                    timing.word_id,
                )
            )

    if not issues:
        return TimingValidationReport((), None, True)
    stage = "alignment" if identities_match else "assembly"
    return TimingValidationReport(tuple(issues), stage, True)


def repair_timings(
    timings: Sequence[NarrationTiming],
    *,
    audio_duration: float,
    chunk_bounds: Mapping[str, TimingBounds],
    minimum_duration: float = 0.02,
) -> tuple[NarrationTiming, ...]:
    """Clamp aligner output without changing word identity or synthesized audio."""

    if minimum_duration <= 0:
        raise ValueError("minimum_duration must be positive")
    repaired: list[NarrationTiming] = []
    previous_start = 0.0
    for timing in timings:
        bounds = chunk_bounds.get(timing.chunk_id)
        if bounds is None:
            raise ValueError(f"No audio bounds for chunk {timing.chunk_id}")
        upper = min(bounds.end, audio_duration)
        lower = max(bounds.start, 0.0, previous_start)
        if upper - lower < minimum_duration:
            raise ValueError(
                f"Chunk {timing.chunk_id} has insufficient room for timing {timing.word_id}"
            )
        start = min(max(timing.start, lower), upper - minimum_duration)
        end = min(max(timing.end, start + minimum_duration), upper)
        repaired_timing = NarrationTiming(
            timing.word_id,
            timing.text,
            round(start, 6),
            round(end, 6),
            timing.chunk_id,
        )
        repaired.append(repaired_timing)
        previous_start = repaired_timing.start
    return tuple(repaired)
