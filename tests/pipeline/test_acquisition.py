from __future__ import annotations

import subprocess

import pytest

from listen_read.pipeline import (
    DefuddleAdapter,
    MissingDefuddleError,
    SourceAcquisitionError,
    acquire_markdown,
)


def test_markdown_input_is_preserved_and_records_provenance() -> None:
    source = acquire_markdown("# A title\n\nKeep *this* exactly.\n", title="A title")

    assert source.markdown == "# A title\n\nKeep *this* exactly.\n"
    assert source.metadata["title"] == "A title"
    assert source.provenance.adapter == "markdown"
    assert source.provenance.version == "1"


def test_defuddle_uses_declared_cli_contract_and_records_version() -> None:
    calls: list[tuple[str, ...]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "defuddle 0.6.3\n", "")
        return subprocess.CompletedProcess(command, 0, "# Extracted\n\nUseful text.\n", "")

    source = DefuddleAdapter(runner=run).acquire("https://example.com/article")

    assert calls == [
        ("defuddle", "--version"),
        ("defuddle", "parse", "https://example.com/article", "--md"),
    ]
    assert source.markdown == "# Extracted\n\nUseful text.\n"
    assert source.provenance.adapter == "defuddle-cli"
    assert source.provenance.version == "defuddle 0.6.3"
    assert source.provenance.command == (
        "defuddle",
        "parse",
        "https://example.com/article",
        "--md",
    )


def test_missing_defuddle_has_actionable_app_owned_install_message() -> None:
    def missing(_: list[str], **__: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("defuddle")

    with pytest.raises(MissingDefuddleError) as error:
        DefuddleAdapter(runner=missing).acquire("https://example.com")

    message = str(error.value)
    assert "defuddle parse <url> --md" in message
    assert "listen-read doctor" in message
    assert "global npm" in message


def test_defuddle_failure_includes_safe_diagnostic_without_page_content() -> None:
    def fail(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "0.6.3\n", "")
        return subprocess.CompletedProcess(command, 1, "secret article text", "network timeout")

    with pytest.raises(SourceAcquisitionError) as error:
        DefuddleAdapter(runner=fail).acquire("https://example.com")

    assert "network timeout" in str(error.value)
    assert "secret article text" not in str(error.value)
