# Listen Read

Listen Read turns URLs and Markdown into a private local listening library: readable article typography, natural on-device narration, exact word highlighting, complete-track preloading, progress, telemetry, and mobile controls in one durable app.

It is an early public release for **Apple Silicon Macs**. Text extraction and the web library are lightweight; natural narration uses MLX, Qwen3-TTS 1.7B CustomVoice, and Qwen3 ForcedAligner. Article content and finished audio stay on the Mac. URL extraction still accesses the source website.

Prerequisites are macOS 14 or newer, Node.js 20.19+, FFmpeg 6+, and UV 0.5+.
`listen-read doctor` reports exact versions and Homebrew repair commands before
setup changes anything. These small system tools are not installed silently;
Defuddle, Python/MLX packages, and models are installed into app-owned storage.

## Quick start

The runtime is currently installed from GitHub through UVX:

```sh
uvx --from git+https://github.com/JayFarei/listen-read listen-read doctor
uvx --from git+https://github.com/JayFarei/listen-read listen-read setup
```

`setup` first prints the compatibility and storage disclosure. The confirmed command installs pinned dependencies under `~/Library/Application Support/Listen Read` and downloads about 5.4 GB of speech/alignment models:

```sh
uvx --from git+https://github.com/JayFarei/listen-read listen-read setup --yes
uvx --from git+https://github.com/JayFarei/listen-read listen-read install-skills
uvx --from git+https://github.com/JayFarei/listen-read listen-read serve --detach
```

Restart the agent host after installing skills, then invoke:

```text
$listen-read https://example.com/article
```

The companion skill reviews Defuddle extraction before submitting the source. The browser also has a baseline URL/Markdown form at [http://127.0.0.1:4242/library](http://127.0.0.1:4242/library).

## Private Tailscale access

Add a single tailnet-only listener without touching other Serve routes:

```sh
uvx --from git+https://github.com/JayFarei/listen-read listen-read expose --https-port 7447
```

Listen Read never enables Funnel and never resets the machine's Tailscale Serve configuration.
The Tailscale listener trusts the tailnet: every principal allowed to reach the
Mac by its tailnet ACL can use the complete library API, including deletion.
Use it only on a personal tailnet or restrict the device/port with Tailscale
ACLs. A future public multi-user release will add per-user pairing.

## What is persisted

The library lives under `~/Library/Application Support/Listen Read` unless `LISTEN_READ_HOME` is set. SQLite holds catalog/job state; article folders hold source Markdown, display and speech projections, FLAC/WAV audio, timings, and telemetry. Delete moves an article to trash; purge is separate. Model and chunk storage are reported independently.

The server survives independently of the heavy narration worker. Jobs run serially, persisted progress is replayed over SSE, interrupted work is recoverable, and the MLX process exits when its queue item finishes so it does not retain unified memory while idle.

## Current pinned speech stack

Verified 14 July 2026 against the official upstream repositories:

- MLX-Audio `64e8416c303fb3b3463dab8eb4ebd78c55a87c1a`
- Qwen3-TTS 1.7B CustomVoice `52f4770fd9726457eae3d3b6aa92047a25a10776`
- Qwen3 ForcedAligner `0e1a68e91d815300c7c9754b2a7639378b23db15`
- Defuddle `0.19.1`

Revisions are immutable for reproducibility. A release update verifies and advances them; normal article creation does not silently upgrade the environment.

## Development

```sh
uv sync --extra test
uv run --extra test pytest
uvx ruff check src tests

cd web
npm ci
npm test
npm run build
npm audit --omit=dev
```

Run the full app with deterministic silent narration for UI/integration work:

```sh
LISTEN_READ_HOME=/tmp/listen-read-dev LISTEN_READ_WORKER=fake \
  uv run listen-read serve --port 4246
```

The architecture and measured 10,068-word scientific-paper production run are documented in [`design/`](design/INDEX.md).

## License

MIT. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for bundled skill attribution.
