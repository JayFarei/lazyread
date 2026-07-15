# Long-paper production run — 14 July 2026

Purpose: ground the Lazyreader system plan in one complete scientific-paper run rather than assumptions from short articles.

## Workload

| Field | Value |
|---|---|
| Source | [LLM-as-a-Verifier: A General-Purpose Verification Framework](https://arxiv.org/html/2607.05391v2) |
| Canonical words | 10,068 |
| Narration chunks | 170 |
| Final audio | 108:03.5 |
| Final FLAC | 125.0 MB |
| Host | Apple M4 Pro, 64 GB unified memory, 12 logical CPUs |
| Speech | Qwen3-TTS 1.7B CustomVoice through MLX-Audio |
| Alignment | Qwen3 ForcedAligner |

## Measured production profile

| Measurement | Result |
|---|---:|
| Source fetch | 3.35 s |
| Initial synthesis and alignment | 70:16.3 |
| Generation speed | 1.54× real time |
| Complete pipeline window, including QA repairs | 89:24.4 |
| Child-process CPU time | 81:50.3 |
| Peak aggregate process RSS | 8.6 GB |
| Peak MLX Metal allocation | 8.8 GB |
| Lowest approximate reclaimable system memory | 9.0 GB |
| Shared model cache | 5.4 GB |
| Temporary chunk audio | 294.6 MB |
| Per-reader Python environment | 342.9 MB |
| Per-reader Node dependencies | 82.3 MB |
| Complete generated reader directory | 1.5 GB |

Energy and GPU-utilization sampling were unavailable because macOS `powermetrics` requires elevated privileges. Process memory, CPU, system-memory sampling, disk changes, and MLX allocation were captured.

## Source-quality findings

The installed Defuddle skill on this Mac used the `defuddle.md` service and produced a strong starting point, but did not make the paper production-ready by itself.

- The References heading was present but bibliography content was absent.
- LaTeXML extraction artifacts had to be removed.
- One broken figure caption required correction.
- Five meaningful figures were visually inspected and given descriptions.
- Mathematical notation, citation keys, algorithm bodies, and captions need different display and speech treatment.

Implication: the skill's document judgment is load-bearing. A runtime-only `add URL` flow can provide a baseline, but it cannot claim the same quality without a structured warning/review mechanism.

The canonical upstream Defuddle skill supplied after this run uses a local CLI instead: `defuddle parse <url> --md`, installed through npm when missing. The run does not establish output parity between those two acquisition paths. Preserve the paper as a comparison fixture before changing adapters.

## Progress finding

The readable source existed after seconds; narration required over an hour. The product must publish the article shell at `text_ready`, then show persisted chunk progress and ETA in that shell and the library. Waiting to reveal anything until `ready` wastes nearly the entire user-visible pipeline.

Generation progress and browser preload are separate phases. After generation, a browser still needs to cache the 125 MB FLAC before Play can be enabled.

## Alignment failures and recovery

The validator found two related defects:

1. an unmatched displayed word received a synthetic fallback time later than the following matched aligner word;
2. trailing fallback timings in two long paragraphs extended beyond their audio chunk and entered the next chunk's timeline.

The reusable correction now:

- enforces monotonic starts inside each mapped chunk;
- bounds start/end values to the chunk's real audio duration;
- retains positive word duration;
- validates monotonicity again over the complete track.

Most importantly, repair reused all 170 cached WAV chunks. Each re-alignment pass took about 78 seconds and did not repeat the 70-minute synthesis.

Implications:

- validation is a publication gate, not an optional test;
- chunk caches must survive alignment/assembly failure;
- job state should distinguish synthesis, alignment, assembly, validation, and publication;
- repair commands should target the cheapest invalid stage.

## Model lifecycle finding

On the final cached re-alignment, model loads took roughly 1.4 seconds in total while the loaded worker retained several gigabytes. Keeping the model worker warm for an hour would trade meaningful memory pressure for negligible latency on this host.

Recommended default:

- lightweight runtime server: remain available for an idle window;
- heavyweight narration worker: exit when the queue drains;
- reconsider a short configurable worker grace period only with measurements on slower supported machines.

## Mobile and reader findings

Desktop rendering passed, but the first 390×844 inspection found a document scroll width of 916 px. Wide research tables and LaTeX-derived expressions were expanding the page.

The template now:

- keeps tables within a locally scrollable region;
- wraps long technical expressions;
- preserves page width at 390 px;
- retains fixed liquid-glass controls and safe-area positioning.

Browser verification also confirmed:

- active word at 207 px against a 211 px top-quarter target;
- Enter play/pause;
- word movement and highlight/undo behavior;
- synchronized playback and active-word updates;
- no console errors;
- byte-range audio serving.

Implication: scientific tables/code/equations belong in the reusable regression suite, not only prose articles.

## Decisions changed by this run

| Before | After evidence |
|---|---|
| Skill could become a thin CLI invocation | Skill remains a first-class document and QA orchestrator |
| Model might stay warm for about an hour | Worker exits when the queue drains by default |
| Paragraph boundaries were sufficient chunking | Chunking must also enforce model and duration limits |
| Alignment retry was one generic job retry | Repair resumes from the cheapest cached stage |
| Responsive prose QA was representative | Scientific tables, equations, code, and long captions are required fixtures |
| Progress could be mostly terminal telemetry | Persisted in-product progress is mandatory for long sources |
| Storage cleanup was a later concern | Model, chunks, finished media, trash, and runtime need separate controls |

## Sources

- [Archived production profile](../../../listening-reader-llm-as-a-verifier/telemetry/profile.md)
- [Generated reader](../../../listening-reader-llm-as-a-verifier/README.md)
- [Current skill](../../SKILL.md)
- [Canonical upstream Defuddle skill](https://github.com/kepano/obsidian-skills/blob/main/skills/defuddle/SKILL.md)
- [arXiv source](https://arxiv.org/html/2607.05391v2)
