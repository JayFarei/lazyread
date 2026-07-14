import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import matter from "gray-matter";
import { JSDOM } from "jsdom";
import { marked } from "marked";
import sanitizeHtml from "sanitize-html";

const inputPath = path.resolve("content/article.md");
const outputPath = path.resolve("src/generated/article.json");
const raw = await readFile(inputPath, "utf8");
const { data, content } = matter(raw);

marked.use({ gfm: true, breaks: false });
const rendered = await marked.parse(content);
const safeHtml = sanitizeHtml(rendered, {
  allowedTags: sanitizeHtml.defaults.allowedTags.concat(["h1", "h2", "img"]),
  allowedAttributes: {
    a: ["href", "title"],
    img: ["src", "alt", "title", "loading"],
  },
  allowedSchemes: ["http", "https", "mailto"],
});

const dom = new JSDOM(`<main id="article-root">${safeHtml}</main>`);
const { document, Node } = dom.window;
const root = document.querySelector("#article-root");
if (!root) throw new Error("Article root was not created");

for (const link of root.querySelectorAll("a")) {
  link.setAttribute("target", "_blank");
  link.setAttribute("rel", "noreferrer");
}

const WORD_PATTERN = /[\p{L}\p{N}]+(?:[’'-][\p{L}\p{N}]+)*/gu;
const blockCandidates = [...root.querySelectorAll("h2, h3, p, li, blockquote")];
const blocks = blockCandidates.filter(
  (element) => !element.querySelector("h2, h3, p, li, blockquote"),
);

let globalWordIndex = 0;
const words = [];
const chunks = [];

for (const [chunkIndex, block] of blocks.entries()) {
  const text = block.textContent?.replace(/\s+/g, " ").trim() ?? "";
  if (!text) continue;

  const firstWordIndex = globalWordIndex;
  const walker = document.createTreeWalker(block, dom.window.NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement?.closest("code, pre")) continue;
    textNodes.push(node);
  }

  for (const textNode of textNodes) {
    const source = textNode.nodeValue ?? "";
    const fragment = document.createDocumentFragment();
    let cursor = 0;

    for (const match of source.matchAll(WORD_PATTERN)) {
      const start = match.index ?? 0;
      const word = match[0];
      if (start > cursor) fragment.append(source.slice(cursor, start));

      const span = document.createElement("span");
      span.className = "spoken-word";
      span.dataset.wordIndex = String(globalWordIndex);
      span.textContent = word;
      fragment.append(span);
      words.push({ index: globalWordIndex, text: word, chunkIndex });
      globalWordIndex += 1;
      cursor = start + word.length;
    }

    if (cursor < source.length) fragment.append(source.slice(cursor));
    textNode.parentNode?.replaceChild(fragment, textNode);
  }

  const lastWordIndex = globalWordIndex - 1;
  if (lastWordIndex >= firstWordIndex) {
    block.classList.add("speech-block");
    block.setAttribute("data-chunk-index", String(chunkIndex));
    chunks.push({
      index: chunkIndex,
      text,
      firstWordIndex,
      lastWordIndex,
      kind: block.tagName.toLowerCase(),
    });
  }
}

const article = {
  metadata: {
    title: String(data.title ?? "Untitled"),
    author: String(data.author ?? data.site ?? "Unknown"),
    site: String(data.site ?? ""),
    source: String(data.source ?? ""),
    description: String(data.description ?? ""),
    published: String(data.published ?? ""),
    wordCount: words.length,
  },
  html: root.innerHTML,
  words,
  chunks,
};

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, JSON.stringify(article, null, 2) + "\n", "utf8");
console.log(
  `Prepared ${chunks.length} narration chunks and ${words.length} highlighted words`,
);
