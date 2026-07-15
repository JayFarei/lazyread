# Lazyread

Turn a URL or Markdown file into a private listening article with natural local
speech, synchronized word highlighting, auto-scroll, and saved highlights.

https://github.com/user-attachments/assets/886577bf-2b03-4c03-8e1c-3cbfb1bdafa2

## Install

Lazyread currently supports Apple Silicon Macs running macOS 14 or newer. It
also needs Node.js 20.19+, FFmpeg 6+, and [UV](https://docs.astral.sh/uv/).

Install the Lazyread skill globally:

```sh
npx --yes skills add https://github.com/jayfarei/lazyread/ --global --agent universal --yes
```

Restart your agent, then invoke the skill with a URL or Markdown file:

```text
$lazyread https://example.com/article
```

On first use, Lazyread explains the local setup and asks before downloading
about 5.4 GB of speech and alignment models. The skill then creates the article,
waits for narration, verifies the reader, and returns a reusable local URL.

## Models, cache, and wait times

Lazyread installs two pinned MLX models into one shared cache for every article:

- **Speech:** `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16`
- **Word alignment:** `mlx-community/Qwen3-ForcedAligner-0.6B-8bit`

The models use about 5.4 GB; allow at least 8 GB of working disk space during
setup. They download only on first-time setup or after the model cache is
removed. Model revisions are pinned per Lazyread release so the same input
remains reproducible.

Narration is generated once and reused. Lazyread keeps temporary speech chunks
so an interrupted job or alignment repair can resume without repeating valid
speech generation. The finished FLAC audio and word timings are stored with the
article. Each browser also downloads the complete finished track into its own
Cache Storage before enabling Play; later listening is immediate and works
offline in that browser.

The readable article appears within seconds, while narration continues in the
background. Generation time depends on article length, Mac hardware, and cache
hits. On the tested M4 Pro:

- the 1,145-word TRACE paper produced 9:38 of audio in 1:11;
- a 10,068-word research paper produced 108:04 of audio in 70:16.

The player may need a little longer to preload the finished track: about 13 MB
for TRACE and 125 MB for the long paper. Another browser or device performs its
own one-time preload. Run `uvx lazyread storage` to see the space used by
articles, temporary chunks, and models.

## What you get

- Natural speech generated locally on your Mac
- Word-by-word tracking and automatic scrolling
- Keyboard navigation, playback speed, and sentence highlights
- A durable private library at `http://127.0.0.1:4242/library`
- Optional private access through your Tailscale network

Article content, audio, highlights, and models remain on your Mac. Creating an
article from a URL still accesses the original website for extraction.

The runtime is also published on [PyPI](https://pypi.org/project/lazyread/).
For development and release details, see [`design/`](design/INDEX.md) and
[`RELEASING.md`](RELEASING.md).

## License

MIT. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
