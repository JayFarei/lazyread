# Lazyreader requirements evolution

Purpose: show how the system requirements emerged through use, so future simplification does not accidentally remove hard-won behavior.

## Evolution

| Stage | Request or observation | Requirement created |
|---|---|---|
| Initial concept | Listen to a URL or Markdown while following highlighted words | Reader-quality rendering, natural narration, exact word synchronization |
| First article | Listening should begin without buffering interruptions | Generate one durable track and fully preload it before Play |
| Private access | Use on localhost and other personal devices | Loopback server plus scoped Tailscale Serve |
| Mobile refinement | Player and controls should feel native and remain usable on a phone | Liquid-glass control system, safe areas, touch targets, responsive layout |
| Reading behavior | Highlight should stay near the top quarter while narration advances | Audio-clock-driven active word and restrained elastic auto-scroll |
| Active reading | Save current/previous sentences and export them for AI | Persisted highlights, copy highlights, flattened article context, undo |
| Keyboard use | Navigate words and paragraphs and toggle playback without Space scrolling | Enter, W/B, P/Shift-P, H/Shift-H, U shortcuts with responsive shortcut legend |
| Article history | A new article should not make the previous one disappear | Durable library, stable article identity, switch, trash, restore |
| Profiling | Understand end-to-end time and local-model resource use | Per-phase telemetry, cache state, memory/CPU/disk measurements, article props |
| Public-launch preparation | Installation, storage, upgrades, progress, and cleanup must become product behavior | Managed runtime, compatibility doctor, central catalog, queue, lifecycle, storage controls |
| Lavish comparison | Borrow a proven install/background-agent shape | On-demand install, detached health-checked server, durable identity |
| User correction | This is Mac-first and model-heavy, not merely a visual plan | Implementation-facing runtime design and explicit model/download/memory lifecycle |
| User correction | The skill performs more work than the proposed CLI boundary allowed | Skill becomes a first-class orchestration and document-quality layer |
| Long arXiv paper | 10,068 words, figures, equations, algorithms, tables, 70-minute generation | Scientific speech policy, persisted progress/ETA, staged repair, table overflow rules, shared storage |
| Canonical Defuddle source supplied | Upstream skill uses a locally installed Node CLI, unlike the hosted-service local copy used for the paper | Declare companion skill/CLI dependency, pin it, avoid silent global npm mutation, and test adapter parity |

## Requirements now considered invariant

- URL and pasted Markdown inputs.
- Semantic, readable display rather than plain text.
- Natural local speech by default with exact provenance.
- Stable word IDs and word-level timings driven by audio time.
- Full-track caching before Play.
- Seek, speed, click-to-seek, keyboard navigation, highlights, undo, and auto-scroll.
- Desktop and mobile behavior verified in a real browser.
- Private localhost access and optional Tailscale Serve.
- One durable article library rather than one app/port per article.
- Persisted processing state and visible progress.
- Cached, resumable, resource-profiled local generation.
- Explicit model, cache, article, and trash lifecycle.
- Skill-level document inspection and final QA.

## Requirements deliberately deferred

- Hosted accounts and cross-device cloud sync.
- Public anonymous web hosting.
- Non-Apple local inference backends.
- Multiple concurrent narration workers.
- Paid hosted speech as the default.
- A native macOS shell before the UVX runtime contract is proven.

## Sources

- [System plan](../lazyreader-system-plan.md)
- [Production findings](production-run-2026-07-14.md)
- [Original research](../../../tts-reader-research-2026-07-13.md)
- [Canonical Defuddle skill](https://github.com/kepano/obsidian-skills/blob/main/skills/defuddle/SKILL.md)
