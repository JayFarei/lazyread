from __future__ import annotations

from listen_read.pipeline import DocumentPipeline, ScientificPolicy, acquire_markdown


PAPER = """# A verifier

The score is $x^2$ according to prior work [3].

![Accuracy chart](chart.png)

## Algorithm 1

Repeat until convergence.

## References
"""


def test_preparation_preserves_display_and_builds_reproducible_speech_projection() -> None:
    acquired = acquire_markdown(PAPER, title="A verifier")
    pipeline = DocumentPipeline(max_chunk_words=5)

    first = pipeline.prepare(acquired, ScientificPolicy())
    second = pipeline.prepare(acquired, ScientificPolicy())

    assert first.display.markdown == PAPER
    assert first.display.document_id == second.display.document_id
    assert first.speech.chunks == second.speech.chunks
    assert all(len(chunk.words) <= 5 for chunk in first.speech.chunks)
    assert len({word.id for word in first.display.words}) == len(first.display.words)
    assert len({word.id for chunk in first.speech.chunks for word in chunk.words}) == sum(
        len(chunk.words) for chunk in first.speech.chunks
    )


def test_scientific_policy_exposes_flags_and_actionable_warnings() -> None:
    prepared = DocumentPipeline().prepare(acquire_markdown(PAPER), ScientificPolicy())
    diagnostics = {item.code: item for item in prepared.diagnostics}

    assert diagnostics["empty_references"].severity == "warning"
    assert diagnostics["figure_description_missing"].severity == "warning"
    assert diagnostics["equations_present"].details["policy"] == "describe"
    assert diagnostics["citations_present"].details["policy"] == "omit_numeric"
    assert diagnostics["algorithms_present"].details["policy"] == "summarize"
    assert "[3]" not in prepared.speech.text
    assert "equation" in prepared.speech.text


def test_policy_and_figure_descriptions_change_projection_identity_not_display_identity() -> None:
    acquired = acquire_markdown(PAPER)
    pipeline = DocumentPipeline()

    baseline = pipeline.prepare(acquired, ScientificPolicy())
    enriched = pipeline.prepare(
        acquired,
        ScientificPolicy(
            figure_descriptions={"Accuracy chart": "A bar chart comparing verifier accuracy."}
        ),
    )

    assert enriched.display.document_id == baseline.display.document_id
    assert enriched.speech.projection_id != baseline.speech.projection_id
    assert "bar chart comparing verifier accuracy" in enriched.speech.text
    assert "figure_description_missing" not in {item.code for item in enriched.diagnostics}


def test_prepared_document_round_trips_through_public_json_contract() -> None:
    prepared = DocumentPipeline(max_chunk_words=7).prepare(
        acquire_markdown("# Hello\n\nA stable document."), ScientificPolicy()
    )

    restored = type(prepared).from_dict(prepared.to_dict())

    assert restored == prepared
    assert restored.schema_version == 1
