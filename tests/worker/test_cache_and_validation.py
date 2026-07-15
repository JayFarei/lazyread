from __future__ import annotations

from lazyread.worker import (
    NarrationTiming,
    NarrationWord,
    TimingBounds,
    chunk_cache_key,
    repair_timings,
    validate_timings,
)


def test_chunk_cache_key_covers_every_synthesis_input() -> None:
    base = {
        "text": "A short passage.",
        "voice": "Aiden",
        "settings": {"temperature": 0.75, "style": "warm"},
        "model_revision": "model@abc",
        "mlx_audio_revision": "mlx-audio@abc",
    }
    key = chunk_cache_key(**base)

    assert key == chunk_cache_key(
        text=base["text"],
        voice=base["voice"],
        settings={"style": "warm", "temperature": 0.75},
        model_revision=base["model_revision"],
        mlx_audio_revision=base["mlx_audio_revision"],
    )
    for changed in (
        {**base, "text": "A different passage."},
        {**base, "voice": "Serena"},
        {**base, "settings": {"temperature": 0.7, "style": "warm"}},
        {**base, "model_revision": "model@def"},
        {**base, "mlx_audio_revision": "mlx-audio@def"},
    ):
        assert chunk_cache_key(**changed) != key


def words() -> tuple[NarrationWord, ...]:
    return (
        NarrationWord("w1", "One", 0),
        NarrationWord("w2", "two", 1),
        NarrationWord("w3", "three", 2),
    )


def test_valid_timings_pass_complete_publication_gate() -> None:
    timings = (
        NarrationTiming("w1", "One", 0.0, 0.2, "c1"),
        NarrationTiming("w2", "two", 0.2, 0.4, "c1"),
        NarrationTiming("w3", "three", 0.5, 0.8, "c2"),
    )
    report = validate_timings(
        timings,
        expected_words=words(),
        audio_duration=1.0,
        chunk_bounds={"c1": TimingBounds(0.0, 0.45), "c2": TimingBounds(0.45, 1.0)},
    )

    assert report.valid
    assert report.issues == ()
    assert report.repair_stage is None


def test_validation_classifies_alignment_repair_without_resynthesis() -> None:
    timings = (
        NarrationTiming("w1", "One", 0.0, 0.3, "c1"),
        NarrationTiming("w2", "two", -0.05, 0.5, "c1"),
        NarrationTiming("w3", "three", 1.1, 1.3, "c2"),
    )
    report = validate_timings(
        timings,
        expected_words=words(),
        audio_duration=1.0,
        chunk_bounds={"c1": TimingBounds(0.0, 0.45), "c2": TimingBounds(0.45, 1.0)},
    )

    assert not report.valid
    assert {issue.code for issue in report.issues} >= {
        "non_monotonic_start",
        "outside_chunk_bounds",
        "outside_audio_bounds",
    }
    assert report.repair_stage == "alignment"
    assert report.reuse_cached_speech is True


def test_alignment_repair_enforces_monotonic_positive_bounded_timings() -> None:
    broken = (
        NarrationTiming("w1", "One", -0.1, 0.1, "c1"),
        NarrationTiming("w2", "two", 0.08, 0.55, "c1"),
        NarrationTiming("w3", "three", 0.4, 1.4, "c2"),
    )
    bounds = {"c1": TimingBounds(0.0, 0.5), "c2": TimingBounds(0.5, 1.0)}

    repaired = repair_timings(broken, audio_duration=1.0, chunk_bounds=bounds)
    report = validate_timings(
        repaired,
        expected_words=words(),
        audio_duration=1.0,
        chunk_bounds=bounds,
    )

    assert report.valid
    assert [timing.start for timing in repaired] == sorted(
        timing.start for timing in repaired
    )
    assert all(timing.start < timing.end for timing in repaired)


def test_word_identity_mismatch_requires_manifest_rebuild_not_timing_clamp() -> None:
    timings = (
        NarrationTiming("w1", "One", 0.0, 0.2, "c1"),
        NarrationTiming("wrong", "TWO", 0.2, 0.4, "c1"),
    )
    report = validate_timings(
        timings,
        expected_words=words(),
        audio_duration=1.0,
        chunk_bounds={"c1": TimingBounds(0.0, 1.0)},
    )

    assert not report.valid
    assert report.repair_stage == "assembly"
    assert report.reuse_cached_speech is True
