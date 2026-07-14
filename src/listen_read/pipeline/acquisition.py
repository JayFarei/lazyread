from __future__ import annotations

from dataclasses import dataclass, field
import subprocess
from typing import Callable, Mapping, Sequence


class SourceAcquisitionError(RuntimeError):
    """A source adapter could not produce usable Markdown."""


class MissingDefuddleError(SourceAcquisitionError):
    """The declared local Defuddle CLI dependency is unavailable."""


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    adapter: str
    version: str
    source_url: str | None = None
    command: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcquiredDocument:
    markdown: str
    provenance: SourceProvenance
    metadata: Mapping[str, str] = field(default_factory=dict)


Runner = Callable[..., subprocess.CompletedProcess[str]]


def acquire_markdown(markdown: str, **metadata: str) -> AcquiredDocument:
    """Accept pasted Markdown without silently rewriting it."""

    if not markdown.strip():
        raise SourceAcquisitionError("Pasted Markdown is empty.")
    return AcquiredDocument(
        markdown=markdown,
        provenance=SourceProvenance(adapter="markdown", version="1"),
        metadata=dict(metadata),
    )


class DefuddleAdapter:
    """Declared adapter for the upstream ``defuddle parse <url> --md`` CLI."""

    def __init__(
        self,
        *,
        executable: str = "defuddle",
        runner: Runner = subprocess.run,
        timeout_seconds: float = 90,
    ) -> None:
        self._executable = executable
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def _run(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MissingDefuddleError(
                "The local Defuddle CLI is required for URL acquisition "
                "(`defuddle parse <url> --md`). Run `listen-read doctor` to "
                "install the pinned app-owned copy; Listen Read will not silently "
                "modify your global npm installation."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SourceAcquisitionError(
                f"Defuddle timed out after {self._timeout_seconds:g}s while fetching the URL."
            ) from exc

    def acquire(self, url: str) -> AcquiredDocument:
        if not url.startswith(("https://", "http://")):
            raise SourceAcquisitionError("Defuddle requires an http:// or https:// URL.")

        version_result = self._run((self._executable, "--version"))
        if version_result.returncode != 0:
            detail = version_result.stderr.strip() or "version check failed"
            raise SourceAcquisitionError(f"Defuddle is present but unusable: {detail}")

        command = (self._executable, "parse", url, "--md")
        result = self._run(command)
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit status {result.returncode}"
            raise SourceAcquisitionError(f"Defuddle could not acquire {url}: {detail}")
        if not result.stdout.strip():
            raise SourceAcquisitionError(
                "Defuddle returned no Markdown; inspect the source or try pasted Markdown."
            )

        return AcquiredDocument(
            markdown=result.stdout,
            provenance=SourceProvenance(
                adapter="defuddle-cli",
                version=version_result.stdout.strip(),
                source_url=url,
                command=command,
            ),
            metadata={"source_url": url},
        )
