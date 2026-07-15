from __future__ import annotations

from dataclasses import dataclass, field
import html as html_module
import http.client
import ipaddress
import re
import socket
import ssl
import subprocess
from typing import Callable, Mapping, Sequence
from urllib.parse import urljoin, urlsplit


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
Resolver = Callable[..., list[tuple]]
Fetcher = Callable[[str], tuple[str, str]]
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5


def _html_with_base(document: str, source_url: str) -> str:
    base = f'<base href="{html_module.escape(source_url, quote=True)}">'
    if re.search(r"<head(?:\s[^>]*)?>", document, flags=re.IGNORECASE):
        return re.sub(
            r"(<head(?:\s[^>]*)?>)",
            rf"\1{base}",
            document,
            count=1,
            flags=re.IGNORECASE,
        )
    return f"<head>{base}</head>{document}"


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Use a validated address while retaining hostname TLS verification."""

    def __init__(self, hostname: str, port: int, address: str, timeout: float):
        super().__init__(
            hostname, port=port, timeout=timeout, context=ssl.create_default_context()
        )
        self._validated_address = address

    def connect(self) -> None:
        self.sock = self._create_connection(
            (self._validated_address, self.port), self.timeout, self.source_address
        )
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def _public_addresses(url: str, resolver: Resolver) -> tuple[str, int, list[str]]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SourceAcquisitionError(
            "URL acquisition requires an http:// or https:// hostname."
        )
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = list(
            dict.fromkeys(
                item[4][0]
                for item in resolver(parsed.hostname, port, type=socket.SOCK_STREAM)
            )
        )
    except socket.gaierror as exc:
        raise SourceAcquisitionError(
            f"Could not resolve the source hostname: {parsed.hostname}"
        ) from exc
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise SourceAcquisitionError(
            "URL acquisition refuses loopback, private, link-local, and reserved network addresses."
        )
    return parsed.hostname, port, addresses


def fetch_public_html(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
    timeout_seconds: float = 30,
) -> tuple[str, str]:
    """Fetch HTML with DNS pinning and validation at every redirect hop."""

    current = url
    for redirect in range(MAX_REDIRECTS + 1):
        hostname, port, addresses = _public_addresses(current, resolver)
        parsed = urlsplit(current)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        connection: http.client.HTTPConnection
        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(
                hostname, port, addresses[0], timeout_seconds
            )
        else:
            connection = http.client.HTTPConnection(
                addresses[0], port=port, timeout=timeout_seconds
            )
        host_header = hostname if port in {80, 443} else f"{hostname}:{port}"
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Host": host_header,
                    "User-Agent": "Lazyread/0.1",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise SourceAcquisitionError(
                        "Source redirect has no Location header."
                    )
                if redirect == MAX_REDIRECTS:
                    raise SourceAcquisitionError("Source exceeded the redirect limit.")
                current = urljoin(current, location)
                continue
            if not 200 <= response.status < 300:
                raise SourceAcquisitionError(
                    f"Source returned HTTP status {response.status}."
                )
            payload = response.read(MAX_SOURCE_BYTES + 1)
            if len(payload) > MAX_SOURCE_BYTES:
                raise SourceAcquisitionError("Source HTML exceeds 10 MiB.")
            charset = response.headers.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace"), current
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise SourceAcquisitionError(
                f"Could not securely fetch the source: {type(exc).__name__}."
            ) from exc
        finally:
            connection.close()
    raise SourceAcquisitionError("Source exceeded the redirect limit.")


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
        resolver: Resolver = socket.getaddrinfo,
        fetcher: Fetcher | None = None,
    ) -> None:
        self._executable = executable
        self._runner = runner
        self._timeout_seconds = timeout_seconds
        self._resolver = resolver
        self._fetcher = fetcher or (
            lambda url: fetch_public_html(
                url, resolver=self._resolver, timeout_seconds=min(timeout_seconds, 30)
            )
        )

    def _run(
        self, command: Sequence[str], *, input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
                **({"input": input_text} if input_text is not None else {}),
            )
        except FileNotFoundError as exc:
            raise MissingDefuddleError(
                "The local Defuddle CLI is required for URL acquisition "
                "(`defuddle parse <url> --md`). Run `lazyread doctor` to "
                "install the pinned app-owned copy; Lazyread will not silently "
                "modify your global npm installation."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SourceAcquisitionError(
                f"Defuddle timed out after {self._timeout_seconds:g}s while fetching the URL."
            ) from exc

    def acquire(self, url: str) -> AcquiredDocument:
        if not url.startswith(("https://", "http://")):
            raise SourceAcquisitionError(
                "Defuddle requires an http:// or https:// URL."
            )

        version_result = self._run((self._executable, "--version"))
        if version_result.returncode != 0:
            detail = version_result.stderr.strip() or "version check failed"
            raise SourceAcquisitionError(f"Defuddle is present but unusable: {detail}")

        html, final_url = self._fetcher(url)
        command = (self._executable, "parse", "-", "--md")
        result = self._run(command, input_text=_html_with_base(html, final_url))
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
            metadata={"source_url": final_url},
        )
