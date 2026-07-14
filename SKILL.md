---
name: listen-read
description: Turn a URL or pasted Markdown into a polished private listening-reader website with natural local speech, synchronized word highlighting, full-track preloading, mobile liquid-glass controls, localhost access, and optional Tailscale access. Use this skill whenever the user wants to listen to an article, essay, plan, notes, or Markdown; asks for a URL-to-audio reader; mentions read-along highlighting, Defuddle, natural local TTS, or a listening site; or invokes “Listen Read”.
---

# Listen Read

Create a finished, private read-along site from one URL or one Markdown document. A successful run ends with a reader-quality page, a complete local narration, exact word timings, a player that cannot start until the whole track is cached, verified URLs, and a durable production profile—not merely a scaffold or instructions.

This workflow targets macOS Apple Silicon and requires Node.js, npm, Python 3.12 via uv, and ffmpeg; Tailscale is optional. The initial local-model download needs network access and roughly 6 GB of disk space.

## Input contract

Accept either:

- a URL to an article or public document; or
- Markdown supplied as a file or pasted directly into the conversation.

If the input is ambiguous, infer from the presence of an `http://` or `https://` URL. Preserve the author's structure and meaning. Do not summarize or rewrite the source unless the user asks.

## Workflow

### 0. Start production telemetry

Profile every external pipeline phase with `scripts/profile_pipeline.py` from the first source fetch through final browser QA. Keep the working report under `/tmp` until scaffolding succeeds, then archive the JSON and rendered Markdown under `<output>/telemetry/` during finalization.

```sh
python3 scripts/profile_pipeline.py run \
  --report /tmp/listen-read-<slug>/profile.json \
  --phase source_fetch \
  -- curl -fsSL <defuddle-url> -o /tmp/listen-read-<slug>/article.md
```

Use short stable phase names such as `source_fetch`, `scaffold`, `node_install`, `content_prepare`, `python_environment`, `audio_generation`, `tests`, `audio_validation`, `build`, `dependency_audit`, `serve_local`, `serve_tailscale`, and `browser_qa`. Pass `--cwd` and `--project` whenever applicable. Do not delete cached models or chunk audio merely to inflate measurements; report whether the run was warm or cold from cache deltas and chunk cache-hit telemetry.

### 1. Canonicalize the document

For a URL, use the `defuddle` skill and fetch `https://defuddle.md/<full-url>`. Inspect the resulting Markdown rather than trusting it blindly:

- remove navigation fragments, previous/next links, cookie text, and obvious extraction debris;
- check lists and linked clauses against the source when something looks truncated;
- inspect meaningful images using the Defuddle image-enrichment rules;
- retain source, author, site, publication date, title, and description in YAML frontmatter.

For pasted Markdown, preserve it exactly apart from adding missing YAML metadata. Derive the title from the first H1 when possible; otherwise use the user's label or ask only if no honest title can be inferred.

Save the canonical Markdown to a temporary file before scaffolding.

### 2. Choose safe ports and destination

Use a durable output directory the user can find. Inspect listeners with `lsof` and inspect `tailscale serve status --json` before choosing ports. Reuse an existing reader port only when updating that same reader.

Never run `tailscale serve reset` as part of this workflow: other private services may share the Serve configuration. Add or replace only the reader's chosen HTTPS port.

### 3. Scaffold the reader

Resolve paths relative to this `SKILL.md`, then run:

```sh
python3 scripts/scaffold_reader.py \
  --markdown /absolute/path/to/article.md \
  --output /absolute/path/to/output-directory \
  --port 4242
```

Use `--title` only when the Markdown has neither frontmatter nor an H1. The helper copies the bundled reader, writes the canonical Markdown, and configures the preview port. Do not hand-recreate the template.

### 4. Prepare the current local speech stack

Naturalness matters more than minimum model size. Use Qwen3-TTS 1.7B CustomVoice through MLX-Audio with the Aiden voice and Qwen3 ForcedAligner. Before each new narration:

1. Verify the current MLX-Audio release/HEAD and current model revisions from the official GitHub and Hugging Face repositories. These projects change regularly; do not reuse an old claim that a revision is “latest.”
2. Install the verified MLX-Audio revision into the reader's `.venv`.
3. Let `generate_audio.py` resolve and record the current immutable Hugging Face revision SHAs in `timings.json`.

Typical setup:

```sh
cd /absolute/path/to/output-directory
npm install
npm run content:prepare
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python \
  "mlx-audio @ git+https://github.com/Blaizzy/mlx-audio.git@<verified-commit>"
npm run generate:audio
```

Generation is paragraph-by-paragraph and cached under `tmp/audio`, so retry after an interruption instead of deleting the cache. The final FLAC is lossless and carries one continuous timeline.

Always run `audio_generation` through the profiler. `generate_audio.py` records model-load time, synthesis and alignment time per chunk, audio duration, cache hits, and MLX Metal peak memory in `timings.json`. The outer profiler records process-tree CPU time, CPU utilization, aggregate resident memory, system memory, disk/cache growth, and machine context. Do not claim GPU utilization or energy usage unless macOS `powermetrics` was explicitly available without interactive elevation; by default, report those as unavailable while retaining MLX Metal allocation and whole-process memory.

### 5. Verify before serving

Run all of:

```sh
npm test
npm run validate:audio
npm run build
npm audit --omit=dev
```

Then check:

- rendered word count equals timing count;
- timestamps are ordered and bounded by the audio duration;
- FLAC duration matches `timings.json`;
- Play stays disabled until `Narration ready offline`;
- playback advances the active word;
- seeking, clicking a word, pausing, speed changes, and long silences stay synchronized;
- no console errors or horizontal overflow at 390×844 mobile viewport;
- the final word can scroll fully above the fixed player.

Use a real browser for these checks, not only HTTP status codes.

### 6. Serve privately

Bind the preview to localhost. Start it using the execution environment's long-lived process mechanism:

```sh
npm run preview
```

Expose a new tailnet-only HTTPS port without disturbing other routes:

```sh
tailscale serve --bg --https=<tailscale-https-port> <local-port>
```

Verify the local page, timing manifest, Tailscale page, and an audio byte-range request. If this Mac cannot resolve its own MagicDNS name, validate with `curl --resolve <dns-name>:<https-port>:<tailscale-ip>`; that resolver quirk does not mean Serve is broken.

After the last finite verification phase, finalize the profile:

```sh
python3 scripts/profile_pipeline.py finalize \
  --report /tmp/listen-read-<slug>/profile.json \
  --project /absolute/path/to/output-directory \
  --manifest /absolute/path/to/output-directory/public/audio/timings.json \
  --source <source-url-or-markdown-label> \
  --archive /absolute/path/to/output-directory/telemetry/profile.json \
  --markdown /absolute/path/to/output-directory/telemetry/profile.md
```

## Reader invariants

Keep these behaviors in every generated site:

- semantic reader layout with headings, lists, links, blockquotes, tables, and meaningful images;
- stable DOM word IDs mapped to aligned timestamps;
- audio time as the sole synchronization clock;
- complete FLAC download into Cache Storage before enabling Play;
- cache-busting audio revision in the manifest;
- click-to-seek, responsive progress rail, speed control, restrained auto-scroll, and light/dark themes;
- mobile liquid-glass controller with safe-area positioning and touch targets at least 40px;
- localhost binding and Tailscale Serve, never Funnel, unless the user explicitly requests public access.

## Handoff

Return the local URL, Tailscale URL when requested, narration duration, word count, exact speech/model revisions, test results, output directory, and telemetry paths. Present pipeline wall time, audio-generation time and real-time factor, CPU time/utilization, peak process memory, MLX Metal peak allocation, disk footprint, and cache status. Clearly distinguish measured values from unavailable energy/GPU-utilization metrics. Mention that the first visit waits for the complete track to cache, after which listening is uninterrupted and available from the browser cache.
