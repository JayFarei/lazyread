---
name: lazyreader
description: Turn a URL, local Markdown file, or pasted Markdown into a durable private listening article with natural local speech, synchronized word highlighting, complete audio preloading, telemetry, a reusable library, localhost access, and optional Tailscale access. Use when the user asks to listen to an article, paper, post, plan, notes, or Markdown; invokes Lazyreader; or wants a read-along audio page.
---

# Lazyreader

Produce an article in the user's single local Lazyreader library. Preserve the source's meaning and structure. Use the companion `defuddle` skill for URL acquisition and source-quality judgment; use the runtime for deterministic storage, narration, progress, serving, and lifecycle.

Use this command prefix until the package is published to PyPI:

```sh
uvx --from git+https://github.com/JayFarei/lazyreader lazyreader
```

## First use

Run `doctor`. If setup is incomplete, run `setup` without `--yes` and show the returned storage/download disclosure. Only after the user confirms, run `setup --yes`. It installs pinned app-owned dependencies and roughly 5.4 GB of local models; do not install global npm packages or download models silently.

Start or reuse the library:

```sh
uvx --from git+https://github.com/JayFarei/lazyreader lazyreader serve --detach
```

Do not start a per-article web server.

## Create an article

For a URL:

1. Invoke the companion `defuddle` skill and save its Markdown to `/tmp/lazyreader-<slug>.md`.
2. Inspect the extraction against the source. Remove navigation debris; preserve metadata, figures, tables, equations, citations, code, lists, and meaning. For scientific sources, flag missing references and add useful descriptions for meaningful figures.
3. Submit the inspected Markdown while retaining the source URL:

```sh
uvx --from git+https://github.com/JayFarei/lazyreader lazyreader add \
  --markdown /tmp/lazyreader-<slug>.md --source-url '<url>' --json
```

For pasted Markdown, save it unchanged to a temporary `.md` file and submit it with `--markdown`. For a local Markdown file, submit the existing file.

The bare browser/CLI URL path is a safe fallback when the companion skill is unavailable, but describe it as unreviewed extraction.

## Observe and verify

Return the stable `/read/<article-id>` route immediately so the user can read while narration runs. Poll `show <article-id> --json`; relay material progress during long jobs. On `failed`, inspect the persisted error and retry only after correcting its cause.

When ready, verify in a real browser:

- semantic readable layout and no page-level overflow at 390x844;
- complete preload finishes before Play is enabled;
- playback, seek, speed, click-to-seek, highlighting, keyboard navigation, and top-quarter auto-scroll;
- synchronized word movement and no console errors.

If Tailscale was requested, inspect existing routes and add one scoped listener:

```sh
uvx --from git+https://github.com/JayFarei/lazyreader lazyreader expose --https-port <unused-port>
```

Never use `tailscale serve reset` and never enable Funnel.

## Handoff

Return local and optional Tailscale URLs, article ID, word count, audio duration, model/aligner revisions, production wall time, CPU time, peak memory, artifact size, cache status, and QA results. Distinguish measured telemetry from unavailable GPU-utilization or energy data.

Use `list`, `trash`, `restore`, `purge`, `storage`, and `clear-cache` for library lifecycle. Explain redownload/regeneration costs before clearing models or chunks.
