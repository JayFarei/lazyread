---
name: defuddle
description: Extract clean markdown content from web pages using Defuddle CLI, removing clutter and navigation to save tokens. Use instead of WebFetch when the user provides a URL to read or analyze, for online documentation, articles, blog posts, or any standard web page. Do NOT use for URLs ending in .md — those are already markdown, use WebFetch directly.
---

# Defuddle

Use Defuddle CLI to extract clean readable content from web pages. Prefer over WebFetch for standard web pages — it removes navigation, ads, and clutter, reducing token usage.

When installed with Lazyread, use its app-owned pinned binary rather than a
global npm package:

```bash
if [ -n "${LAZYREAD_HOME:-}" ]; then
  LAZYREAD_DATA_HOME="$LAZYREAD_HOME"
elif [ -n "${LAZYREADER_HOME:-}" ]; then
  LAZYREAD_DATA_HOME="$LAZYREADER_HOME"
elif [ -n "${LISTEN_READ_HOME:-}" ]; then
  LAZYREAD_DATA_HOME="$LISTEN_READ_HOME"
elif [ -d "$HOME/Library/Application Support/Lazyread" ]; then
  LAZYREAD_DATA_HOME="$HOME/Library/Application Support/Lazyread"
elif [ -d "$HOME/Library/Application Support/Lazyreader" ]; then
  LAZYREAD_DATA_HOME="$HOME/Library/Application Support/Lazyreader"
else
  LAZYREAD_DATA_HOME="$HOME/Library/Application Support/Listen Read"
fi
DEFUDDLE_BIN="$LAZYREAD_DATA_HOME/runtime/defuddle/node_modules/.bin/defuddle"
```

If that path is absent, use `command -v defuddle` when an existing installation
is available. Otherwise run the Lazyread `setup` disclosure flow; do not
silently install a global npm package.

## Usage

Always use `--md` for markdown output:

```bash
"$DEFUDDLE_BIN" parse <url> --md
```

Save to file:

```bash
"$DEFUDDLE_BIN" parse <url> --md -o content.md
```

Extract specific metadata:

```bash
"$DEFUDDLE_BIN" parse <url> -p title
"$DEFUDDLE_BIN" parse <url> -p description
"$DEFUDDLE_BIN" parse <url> -p domain
```

## Output formats

| Flag | Format |
|------|--------|
| `--md` | Markdown (default choice) |
| `--json` | JSON with both HTML and markdown |
| (none) | HTML |
| `-p <name>` | Specific metadata property |
