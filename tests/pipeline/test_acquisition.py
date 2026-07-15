from __future__ import annotations

import subprocess

import pytest

from listen_read.pipeline import acquisition
from listen_read.pipeline import (
    DefuddleAdapter,
    MissingDefuddleError,
    SourceAcquisitionError,
    acquire_markdown,
)


def public_resolver(*_args: object, **_kwargs: object) -> list[tuple]:
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def test_markdown_input_is_preserved_and_records_provenance() -> None:
    source = acquire_markdown("# A title\n\nKeep *this* exactly.\n", title="A title")

    assert source.markdown == "# A title\n\nKeep *this* exactly.\n"
    assert source.metadata["title"] == "A title"
    assert source.provenance.adapter == "markdown"
    assert source.provenance.version == "1"


def test_defuddle_uses_declared_cli_contract_and_records_version() -> None:
    calls: list[tuple[str, ...]] = []
    inputs: list[str] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "defuddle 0.6.3\n", "")
        inputs.append(str(kwargs["input"]))
        return subprocess.CompletedProcess(command, 0, "# Extracted\n\nUseful text.\n", "")

    source = DefuddleAdapter(
        runner=run,
        resolver=public_resolver,
        fetcher=lambda url: ("<main>Useful text.</main>", url),
    ).acquire("https://example.com/article")

    assert calls == [
        ("defuddle", "--version"),
        ("defuddle", "parse", "-", "--md"),
    ]
    assert source.markdown == "# Extracted\n\nUseful text.\n"
    assert source.provenance.adapter == "defuddle-cli"
    assert source.provenance.version == "defuddle 0.6.3"
    assert source.provenance.command == (
        "defuddle",
        "parse",
        "-",
        "--md",
    )
    assert '<base href="https://example.com/article">' in inputs[0]


def test_missing_defuddle_has_actionable_app_owned_install_message() -> None:
    def missing(_: list[str], **__: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("defuddle")

    with pytest.raises(MissingDefuddleError) as error:
        DefuddleAdapter(
            runner=missing,
            fetcher=lambda url: ("<main>text</main>", url),
        ).acquire("https://example.com")

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
        DefuddleAdapter(
            runner=fail,
            resolver=public_resolver,
            fetcher=lambda url: ("<main>secret article text</main>", url),
        ).acquire("https://example.com")

    assert "network timeout" in str(error.value)
    assert "secret article text" not in str(error.value)


def test_defuddle_rejects_private_and_loopback_sources_before_fetching() -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "0.19.1", "")

    def private_resolver(*_args: object, **_kwargs: object) -> list[tuple]:
        return [(2, 1, 6, "", ("127.0.0.1", 80))]

    with pytest.raises(SourceAcquisitionError, match="refuses loopback"):
        DefuddleAdapter(runner=run, resolver=private_resolver).acquire("http://localhost/admin")

    assert calls == [["defuddle", "--version"]]


def test_secure_fetch_pins_the_public_address_and_rejects_a_private_redirect(
    monkeypatch,
) -> None:
    requests: list[tuple[str, int, str, str]] = []

    class RedirectResponse:
        status = 302

        @staticmethod
        def getheader(name: str) -> str | None:
            return "http://internal.example/admin" if name == "Location" else None

    class Connection:
        def __init__(self, host: str, port: int, timeout: float):
            requests.append((host, port, "", ""))

        def request(self, method: str, path: str, headers: dict[str, str]) -> None:
            host, port, _, _ = requests[-1]
            requests[-1] = (host, port, method, headers["Host"])

        @staticmethod
        def getresponse() -> RedirectResponse:
            return RedirectResponse()

        @staticmethod
        def close() -> None:
            return None

    def resolver(host: str, *_args: object, **_kwargs: object) -> list[tuple]:
        address = "93.184.216.34" if host == "public.example" else "127.0.0.1"
        return [(2, 1, 6, "", (address, 80))]

    monkeypatch.setattr(acquisition.http.client, "HTTPConnection", Connection)

    with pytest.raises(SourceAcquisitionError, match="refuses loopback"):
        acquisition.fetch_public_html(
            "http://public.example/article", resolver=resolver
        )

    assert requests == [("93.184.216.34", 80, "GET", "public.example")]
