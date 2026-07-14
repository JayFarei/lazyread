# Listen Read design decisions

Purpose: record the decisions that future implementation work should treat as defaults unless new evidence explicitly overturns them.

## Decision summary

| ID | Decision | Status |
|---|---|---|
| D-01 | Skill and runtime are complementary product layers | Accepted |
| D-02 | Runtime is a Python CLI/application distributed through UVX | Accepted for implementation |
| D-03 | One runtime and library replace per-article applications | Accepted |
| D-04 | Display document and speech projection are separate artifacts | Accepted |
| D-05 | Server and model worker have separate idle lifecycles | Accepted |
| D-06 | Narration concurrency is one job for version one | Accepted |
| D-07 | SQLite plus filesystem artifacts is the local persistence model | Accepted |
| D-08 | Validation gates publication and recovery reuses the cheapest cache | Accepted |
| D-09 | Version one supports Apple Silicon Macs | Accepted |
| D-10 | Localhost is default; Tailscale Serve is optional and private | Accepted |
| D-11 | Complete audio preload remains a reader invariant | Accepted, with long-form review |
| D-12 | Defuddle skill and CLI are declared dependencies; exact Node/CLI installation shape remains open | Partially accepted |

## D-01 — Skill and runtime are complementary product layers

The skill owns source-specific judgment: extraction inspection, cleanup, figure understanding, speech policy, current-stack verification, browser QA, and handoff. The runtime owns deterministic mechanics: installation, models, jobs, storage, serving, telemetry, and lifecycle.

Rejected: reducing the skill to `listen-read add <url>`. The scientific-paper run showed that the quality gap lives exactly in the work a thin wrapper would remove.

## D-02 — UVX distribution

Package the CLI/runtime as a Python application launched by UVX. Ship the compiled web app as package data.

Rationale: the local inference stack is Python-native, UVX provides isolated application execution, and the same runtime can be called from multiple agent hosts. Lavish remains prior art for lifecycle shape, not a requirement to use npm.

Rejected: one npm/venv/Vite application per article. Deferred: native `.pkg` or menu-bar wrapper until the runtime contract stabilizes.

## D-03 — One runtime and library

Articles receive UUID identity and `/read/:id` routes inside one application. A single catalog, environment, model cache, server, and optional Tailscale route serve all articles.

Rationale: current generated readers duplicate hundreds of megabytes of runtime dependencies and lose availability when their individual preview server exits.

## D-04 — Display and speech are separate

Preserve a semantic display document and a source-linked speech projection. Store the policy and mappings as versioned artifacts.

Rationale: equations, citations, figures, code, tables, footnotes, and algorithms should not necessarily be spoken as displayed.

## D-05 — Two-tier lifecycle

Keep the lightweight server available for a modest idle period, but unload the model worker when the queue drains.

Rationale: cached model loading was roughly 1.4 seconds on the measured host; retained worker memory is several gigabytes. A one-hour model warm period is a poor default.

## D-06 — One narration job

Queue narration jobs rather than running models concurrently in version one.

Rationale: observed MLX peaks across runs are material on unified-memory systems. Queue progress and ETA are safer and simpler than opportunistic parallelism.

## D-07 — SQLite plus files

SQLite stores catalog, jobs, progress, settings, highlights, provenance, and deletion state. Article documents, audio, timings, images, and telemetry remain files.

Rationale: crash-safe transitions and migrations require more than JSON session files, while large blobs do not belong in SQLite.

## D-08 — Validation and staged recovery

An article becomes `ready` only after audio, timing, build, security, and browser gates pass. A failure retries only the invalid stage and preserves compatible caches.

Rationale: the long-paper validator prevented a broken binary-search timing index from being published and repaired it without speech regeneration.

## D-09 — Apple Silicon first

Version one supports macOS arm64 with MLX. Unsupported systems fail in `doctor` before model downloads.

Rationale: this is the proven stack. Cross-platform inference would create a backend, packaging, performance, and QA matrix before the product surface is stable.

## D-10 — Private networking

Bind the server to loopback. Add Tailscale Serve only when requested, on a scoped route. Never reset unrelated Serve configuration and never enable Funnel implicitly.

## D-11 — Complete preload

Play is enabled only when the revisioned complete track is in browser Cache Storage. Narration-generation progress and browser-download progress remain separate.

Rationale: uninterrupted, seekable, offline-capable playback is a core experience. The 125 MB long-paper result requires visible download progress and may motivate multi-track chapters for book-sized sources, but not silent streaming degradation.

## D-12 — Defuddle is a declared companion dependency

The canonical upstream Defuddle skill uses the local `defuddle` Node CLI and recommends installing it globally with npm when missing. Listen Read should ship/install the companion skill and invoke a pinned CLI adapter rather than reimplement extraction inside the Python runtime.

The remaining decision is operational: install Defuddle into app-owned storage, adopt a compatible existing global install, or bundle its Node runtime. The app-owned pinned installation is the current recommendation because it avoids silent global mutation and enables deterministic upgrades and cleanup.

The locally installed skill used for the long-paper run calls the hosted `defuddle.md` service instead. Output parity with the upstream CLI must be tested before migration.

## Sources

- [System plan](../listen-read-system-plan.md)
- [Production run](production-run-2026-07-14.md)
- [Current skill](../../SKILL.md)
- [Canonical Defuddle skill](https://github.com/kepano/obsidian-skills/blob/main/skills/defuddle/SKILL.md)
- [Lavish CLI/runtime prior art](https://github.com/kunchenguid/lavish-axi)
