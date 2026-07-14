---
name: defuddle
description: Extract clean markdown content from web pages using Defuddle CLI, removing clutter and navigation to save tokens. Use instead of WebFetch when the user provides a URL to read or analyze, for online documentation, articles, blog posts, or any standard web page. Do NOT use for URLs ending in .md — those are already markdown, use WebFetch directly.
---

# Defuddle

Use Defuddle CLI to extract clean readable content from web pages. Prefer over WebFetch for standard web pages — it removes navigation, ads, and clutter, reducing token usage.

When installed with Listen Read, use its app-owned pinned binary rather than a
global npm package:

```bash
DEFUDDLE_BIN="${LISTEN_READ_HOME:-$HOME/Library/Application Support/Listen Read}/runtime/defuddle/node_modules/.bin/defuddle"
```

If that path is absent, use `command -v defuddle` when an existing installation
is available. Otherwise run the Listen Read `setup` disclosure flow; do not
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
