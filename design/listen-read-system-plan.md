# Listen Read system plan

Status: revised after the 14 July 2026 long-paper production run  
Scope: macOS on Apple Silicon, local-first, private by default

## Outcome

A user invokes the Listen Read skill with a URL or pasted Markdown and receives a stable article route in one local listening library. The article becomes readable shortly after extraction; narration progress appears in the article and library; the final track is locally generated, fully cached before playback, synchronized word by word, and available through localhost and optionally Tailscale.

The product is distributed as two cooperating units:

1. **Listen Read skill** — judgment, source understanding, policy, orchestration, and final verification.
2. **Listen Read runtime** — deterministic installation, storage, local-model execution, job state, web serving, telemetry, and lifecycle.

The runtime must not flatten the skill into `add <url>`. The skill is a load-bearing part of the product.

## Product principles

- One installed runtime, one web application, one library, many articles.
- The skill owns decisions that depend on what kind of document it is reading.
- The runtime owns operations that must behave identically every time.
- Text is useful before audio is ready; narration progress belongs in the reading experience.
- Audio time is the only synchronization clock.
- Every expensive step is cached, resumable, measurable, and independently validatable.
- Localhost is the default trust boundary. Tailscale Serve is private reachability, never accidental Funnel exposure.
- A failed article remains inspectable and retryable; it never silently disappears.

## Skill and runtime are complementary

| Listen Read skill owns | Runtime and CLI own |
|---|---|
| Interpret the user invocation and source intent | System compatibility checks and actionable `doctor` output |
| Choose URL, pasted Markdown, or local-file acquisition path | Install/update the Python package, static web assets, and runtime environment |
| Invoke the companion Defuddle skill when appropriate and inspect extraction quality | Ensure and invoke the pinned Defuddle CLI adapter; persist source payloads, canonical documents, artifacts, jobs, and settings |
| Remove extraction debris without changing meaning | Run deterministic prepare, narrate, align, assemble, validate, and publish commands |
| Preserve metadata and source structure | Resolve and record immutable model/tool revisions |
| Inspect meaningful figures and add useful visual descriptions | Own model and chunk caches and report their storage use |
| Decide how equations, citations, algorithms, code, tables, and images should be spoken | Enforce chunk duration, timing monotonicity, word identity, and audio bounds |
| Verify the latest supported speech stack before a new release/channel update | Queue jobs, recover interrupted work, emit events, and calculate ETA |
| Perform browser QA and judge whether the reader is genuinely usable | Serve one stable library URL and optional Tailscale adapter |
| Explain results, limitations, provenance, and measured resources | Import, list, read, trash, restore, purge, retry, and cancel records |

The runtime exposes a compact structured interface. The skill may call several commands during one invocation rather than delegating the entire experience to a single opaque command.

Illustrative flow:

```text
$listen-read <source>
  skill: acquire and inspect source
  skill: produce canonical display document + speech policy
  runtime: ensure/doctor
  runtime: submit prepared article
  skill: observe persisted progress and resolve recoverable failures
  runtime: narrate, align, validate, publish
  skill: browser-QA the result and hand back stable URLs + profile
```

The browser “Add” form and bare CLI can support a safe baseline pipeline for people without an agent. The skill path remains the highest-quality path because it can reason about source-specific defects and enrichments.

## Target architecture

```text
Agent skill                 Browser Add form                 Direct CLI
    │                              │                              │
    └──────── source / prepared document / policy ───────────────┘
                                   │
                         Listen Read runtime
                 health · version · queue · SSE · auth boundary
                    │              │                │
             document pipeline   library        narration worker
                    │              │                │
            canonical display   SQLite         MLX-Audio + Qwen
            + speech projection  + files        JSONL event seam
                    │              │                │
                    └──────── reader web app ───────┘
                         /library · /read/:id
```

External runtime interface:

```text
doctor()
ensure_runtime()
submit(source | prepared_document, policy) -> article_id
observe(article_id) -> snapshot + event stream
list(), read(article_id)
cancel(), retry()
trash(), restore(), purge()
storage(), clear_cache(scope)
```

Internal modules should stay deep:

- **Runtime:** process lifecycle, compatibility, migrations, queue, recovery, events, stable server identity, and adapters.
- **Library:** catalog transactions, blob writes, atomic publish, highlights, deletion, import, and storage accounting.
- **Document pipeline:** source adapters, canonical display document, speech projection, stable token identity, and content-policy diagnostics.
- **Narration worker:** model loading, chunk cache, synthesis, alignment, assembly, timing invariants, and resource telemetry.
- **Reader:** library and article routes, cached playback, synchronized reading, highlights, progress, accessibility, and responsive layout.

## Distribution and installation

### Packaging choice

Distribute the runtime as a Python application runnable with UVX:

```sh
uvx listen-read doctor
uvx listen-read serve --detach
uvx listen-read add --prepared /path/to/document.json
```

Why UVX rather than copying Lavish's `npx -y` literally:

- the inference stack is already Python and MLX-based;
- UV provides isolated, versioned application environments and Python selection;
- compiled web assets can ship inside the Python wheel;
- the skill can invoke the same command from Codex, Claude Code, or another host;
- a thin native installer can be added later without changing the runtime interface.

Borrow Lavish's operational shape—on-demand installation, detached server, health/version checks, and durable identity—not its package manager.

### Shipped unit

The repository/release contains:

```text
listen-read/
├── skills/
│   ├── listen-read/SKILL.md
│   └── defuddle/SKILL.md      # pinned upstream companion skill
├── src/listen_read/          # Python CLI and runtime
├── web/dist/                 # prebuilt reader/library assets
├── migrations/
├── worker/                   # MLX narration worker
└── pyproject.toml
```

Host-specific installers place both versioned skills in the appropriate skills directory. The Listen Read skill depends on the companion Defuddle skill for URL acquisition and on the versioned runtime contract for deterministic production. Pasted Markdown remains usable when URL extraction is unavailable.

The [canonical Defuddle skill](https://github.com/kepano/obsidian-skills/blob/main/skills/defuddle/SKILL.md) invokes a local Node CLI and recommends `npm install -g defuddle` when it is missing. For a portable Listen Read release, installation must not silently mutate the user's global npm environment. The runtime should prefer a pinned, app-owned Defuddle installation under Application Support; a user-approved global installation can be adopted when compatible.

### Compatibility contract

Version one supports Apple Silicon Macs only. `listen-read doctor` checks before downloading models:

- macOS and arm64 architecture;
- supported OS version;
- available RAM and reclaimable memory;
- free disk space for the application, 5.4 GB shared model cache, working audio, and finished library;
- `uv` availability or guided bootstrap;
- a compatible Node runtime and pinned Defuddle CLI, or the ability to install them into app-owned storage;
- `ffmpeg` availability or managed installation path;
- local port and optional Tailscale status;
- runtime/schema/model channel compatibility.

The installation prompt must state expected downloads and working storage before proceeding. Unsupported Intel Macs and non-Mac systems receive an explicit compatibility result, not an attempted MLX installation.

## Document pipeline

### Two related representations

Every article preserves:

1. **Display document:** headings, lists, links, figures, captions, tables, equations, code, footnotes, and source metadata.
2. **Speech projection:** the exact narration text, broken into bounded chunks, with stable mappings back to displayed tokens.

This separation is mandatory for scientific and technical material. The display document should not be damaged to make the speech sound natural.

### Source acquisition

- URL through the skill: use the companion Defuddle skill, which runs `defuddle parse <url> --md`, then inspect the result.
- Pasted Markdown: preserve it apart from missing metadata and explicit user-approved cleanup.
- Prepared file: import directly with recorded provenance.
- Browser/bare CLI baseline: use a documented source adapter and surface extraction warnings when agent review is unavailable.

Defuddle is a local CLI dependency that fetches the target page over the network; it is not a local model and it does not require the `defuddle.md` hosted service. The upstream skill tells agents to install it globally with npm when missing. Listen Read should instead pin its version and manage it in app-owned storage so extraction is reproducible and cleanup is honest.

The local Defuddle skill used for the 14 July paper currently differs from that upstream contract and calls the `defuddle.md` service. That production run therefore proves the downstream canonicalization and reader pipeline, but it does not prove output parity with the upstream Defuddle CLI. Add a comparison fixture before switching the production adapter.

### Scientific-document policy

The arXiv run establishes dedicated rules:

- verify bibliography extraction; an empty References heading is a warning, not a successful extraction;
- keep equations visible while generating concise, natural spoken equivalents;
- normally render citation keys visually but omit or naturalize them in speech;
- keep algorithm bodies visible and narrate a concise summary unless the user requests line-by-line reading;
- inspect meaningful figures and attach a spoken visual description;
- make tables locally horizontally scrollable and long expressions wrap without expanding the page;
- bound chunk size by speech duration/token limits, not only source paragraph boundaries.

The skill chooses or confirms these policies. The runtime records them in an immutable article manifest so regeneration is reproducible.

## Persisted jobs and progress

Persist every state transition before broadcasting it. Reconnecting clients receive a snapshot first and then Server-Sent Events.

```text
queued
acquiring
canonicalizing
text_ready
preparing
narrating (chunk 63 / 170, ETA 44m)
aligning
assembling
validating
preloading_available
ready

interrupted -> resumable
failed -> retryable | requires_skill_review
cancelling -> cancelled
trashed -> purging -> purged
```

Progress surfaces:

- return `/read/:id` immediately after the article record exists;
- show readable text as soon as `text_ready` is reached;
- show phase, completed/total chunks, elapsed time, rolling ETA, cache hits, and any warning at the top of the article;
- show the same compact progress on its library card;
- distinguish narration generation from browser download/preload progress;
- retain the completed production profile in article props.

The 10,068-word paper took 3.35 seconds to fetch but 70 minutes to synthesize. A terminal-only progress stream is therefore not acceptable product behavior.

## Two-tier lifecycle

The lightweight server and the heavy model worker have different lifecycles.

### Runtime server

- starts on demand after a health/version check;
- never stops while a job, browser client, or SSE subscriber is active;
- may remain available for 30 minutes of inactivity;
- preserves all state in SQLite/files, so a restart does not change article identity.

### Narration worker

- one worker/job at a time for version one;
- loads models only when narration or alignment is required;
- exits when the queue drains, releasing MLX/Metal memory;
- does not stay warm for an hour by default.

The measured model load was roughly 1.4 seconds on the tested M4 Pro, while the loaded worker retained several gigabytes and peaked at 8.8 GB of MLX allocation. A long warm timeout saves little and creates disproportionate memory pressure. A future configurable short grace period is allowed only when measurements on supported machines show a meaningful latency benefit.

## Storage and cache lifecycle

```text
~/Library/Application Support/Listen Read/
├── listen-read.sqlite
├── articles/<article-id>/
│   ├── source.md
│   ├── document.json
│   ├── speech.json
│   ├── audio.flac
│   ├── timings.json
│   ├── telemetry.json
│   └── images/
├── cache/
│   ├── models/
│   └── chunks/
├── runtime/
├── logs/
└── trash/
```

Rules:

- SQLite stores relational state; large immutable artifacts remain files.
- Writes publish atomically only after validation.
- Chunk keys include normalized speech text, voice, settings, and immutable model revision.
- Failed validation never deletes valid synthesized chunks.
- Intermediate WAVs may be removed after validated FLAC publication according to retention policy.
- Storage UI separates articles, temporary chunks, models, runtime, and trash.
- “Clear temporary chunks” and “remove downloaded models” explain regeneration/redownload consequences.
- Delete moves an article to a seven-day trash by default; purge is separate.

The long paper produced a 125 MB FLAC and 294.6 MB of temporary chunks. Storage management is part of the core product, not a later preference screen.

## Validation and repair

Publication is gated by all of:

- displayed word identity and count match the timing manifest;
- starts are monotonic across the complete track;
- every timing has positive duration and remains inside its audio chunk and final track;
- audio duration and manifest duration agree;
- model, aligner, and tool revisions are immutable and recorded;
- complete FLAC can be cached and served with byte ranges;
- tests, production build, and dependency audit pass;
- real-browser QA passes on desktop and 390×844 mobile with no page-level horizontal overflow;
- playback, seek, word click, speed, Enter toggle, word/paragraph shortcuts, highlighting, undo, and top-quarter auto-scroll behave correctly;
- no console errors.

The repair path is staged:

1. canonicalization failure -> skill review, no narration;
2. synthesis failure -> retry only missing chunks;
3. alignment failure -> re-align cached WAVs without speech regeneration;
4. assembly/manifest failure -> rebuild from cached chunks;
5. browser/layout failure -> rebuild web assets without touching audio;
6. publish only after every gate succeeds.

This is not theoretical: validation of the arXiv paper found non-monotonic timings caused first by synthetic fallback words and then by spill across chunk boundaries. The system repaired alignment from 170 cached chunks in 78 seconds instead of repeating 70 minutes of synthesis.

## Reader and library experience

### Stable routes

```text
/library
/read/:article-id
/settings/storage
```

One permanent localhost origin replaces per-article ports. Tailscale Serve points one stable tailnet-only HTTPS route at that origin.

### Article header props

- source, author, publication date, created date;
- word count and narration duration;
- current phase and progress while processing;
- voice, model/tool revisions, and local/hosted provider;
- production time, real-time factor, peak memory, artifact size, and cache state;
- extraction or speech-policy warnings.

### Library

- ready, processing, failed, and trashed sections;
- search and sort by recent/source/title;
- compact progress and ETA on processing cards;
- switch articles without starting another server;
- trash, restore, purge, retry, and storage actions;
- persisted highlights accessible across localhost and Tailscale clients.

### Full-track preload

Play remains disabled until the complete revisioned FLAC is in Cache Storage. The UI shows bytes and percentage separately from narration generation. For long papers, the user sees the readable article while the 125 MB track downloads; once cached, playback is uninterrupted and offline-capable in that browser.

## Telemetry contract

Each job records phase wall time, child-process CPU time, process-tree CPU, peak and mean RSS, lowest reclaimable system memory, disk/cache deltas, chunk synthesis/alignment times, cache hits, audio duration, real-time factor, and MLX Metal allocation.

Do not claim GPU utilization or energy use when macOS requires elevated `powermetrics`. Mark those unavailable while retaining process and MLX measurements.

Telemetry serves three audiences:

- **user:** progress, ETA, storage, and understandable resource expectations;
- **skill:** evidence for retries, warnings, and final handoff;
- **development:** regression profiles across model/tool releases and supported hardware tiers.

## Security and privacy

- bind only to `127.0.0.1` by default;
- Tailscale Serve is an explicit opt-in adapter and must modify only its assigned route;
- never use Funnel unless the user explicitly requests public exposure;
- record the Defuddle CLI version and target URL; separately disclose if a hosted extraction fallback or hosted speech provider received text;
- local model narration has no per-article API charge and keeps speech text on-device after acquisition;
- sanitize rendered content and never execute source scripts;
- treat source URLs and article text as untrusted input;
- keep logs free of full article content unless diagnostic mode is explicitly enabled.

## Implementation sequence

Each milestone leaves a useful, testable product and preserves the checkpoint at commit `5a37f58`.

### 1. Runtime skeleton and package boundary

- create the Python package, UVX entry point, compatibility doctor, versioned config, and embedded web build;
- define the skill/runtime protocol and prepared-document manifest;
- declare and verify the companion Defuddle skill/CLI contract without silently changing global npm state;
- add fake document and narration workers for fast tests;
- acceptance: the skill can ensure and health-check one detached runtime without installing per-article environments.

### 2. Central library and stable reader routes

- add SQLite migrations, article UUIDs, filesystem blob store, atomic publication, `/library`, and `/read/:id`;
- import the existing readers without deleting or moving originals;
- acceptance: all imported articles remain reachable after a runtime restart from one stable origin.

### 3. Persisted pipeline and progress

- implement job state machine, one-job queue, JSONL worker seam, SSE snapshot/reconnect, ETA, cancellation, retry, and crash recovery;
- expose text before narration completes;
- acceptance: kill the process mid-paper, restart it, and resume from cached chunks with accurate UI state.

### 4. Shared speech stack and storage controls

- install one MLX environment and one app-owned model cache;
- implement two-tier server/worker lifecycle, cache provenance, storage totals, chunk cleanup, model removal, and seven-day trash;
- acceptance: completing a job releases model memory while the library remains available.

### 5. Scientific-document quality and repair gates

- formalize display/speech projections and policies for equations, citations, algorithms, figures, tables, code, and bibliography warnings;
- enforce bounded/monotonic timings and staged repair;
- acceptance: the 10,068-word arXiv paper imports, regenerates or reuses cache, validates, and passes mobile/browser QA.

### 6. Skill distribution and release hardening

- package the versioned skill and UVX runtime together;
- add stable/beta model channels, signed/reproducible release process, upgrade/migration tests, install-size disclosure, privacy copy, and uninstall/cleanup;
- acceptance: a fresh supported Mac can invoke `$listen-read <url>`, approve the stated downloads, and receive one stable article route without manual dependency work.

## Release acceptance criteria

- fresh-install and warm-install flows tested on supported Apple Silicon memory tiers;
- compatibility failures occur before multi-gigabyte downloads;
- one shared model/runtime installation serves every article;
- source text appears independently of narration completion;
- progress and ETA survive refresh and runtime restart;
- only one narration job consumes model memory at a time;
- worker memory is released when the queue drains;
- interrupted generation resumes from compatible chunks;
- validation failures cannot publish a ready article;
- library, highlights, trash, restore, storage, localhost, and Tailscale flows pass browser QA;
- the exact article/model/tool provenance and production profile remain inspectable;
- uninstall offers separate choices for application, articles, temporary cache, and downloaded models.

## Open decisions

1. **Defuddle installation:** pinned app-owned npm installation is recommended; verify whether to bundle a Node runtime or require one, and define how an existing global Defuddle installation is adopted. Compare upstream CLI output with the current `defuddle.md` workflow before migration.
2. **Minimum supported unified memory:** run the same representative short article and long paper on lower-memory Apple Silicon machines before setting the floor and warning thresholds.
3. **Public launch shape:** local downloadable product is the recommended first release; account-based hosted sync remains outside the first runtime milestone.
4. **Full-track preload ceiling:** preserve complete preload by default, but test whether very long books need explicit multi-track chapters while retaining uninterrupted per-chapter playback.
5. **Stable model channel cadence:** define how new MLX-Audio/model revisions graduate after regression comparison, rather than checking “latest” independently during every end-user job.

## Evidence

- [Current Listen Read skill](../SKILL.md)
- [Canonical Defuddle skill](https://github.com/kepano/obsidian-skills/blob/main/skills/defuddle/SKILL.md)
- [Lavish CLI/runtime prior art](https://github.com/kunchenguid/lavish-axi)
- [Long-paper production findings](materials/production-run-2026-07-14.md)
- [Design decisions](materials/design-decisions-log.md)
- [Requirements evolution](materials/requirements-evolution.md)
- [Original synchronized-reader research](../../tts-reader-research-2026-07-13.md)
