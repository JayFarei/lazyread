import { marked } from "marked";
import type { WordTiming } from "./types";

const BLOCKED = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "BUTTON", "LINK", "META"]);

export function sanitizeArticle(html: string): string {
  const document = new DOMParser().parseFromString(`<main>${html}</main>`, "text/html");
  const root = document.body.firstElementChild;
  if (!root) return "";
  for (const element of [...root.querySelectorAll("*")]) {
    if (BLOCKED.has(element.tagName)) { element.remove(); continue; }
    for (const attribute of [...element.attributes]) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim().toLowerCase();
      if (name.startsWith("on") || name === "style" || name === "srcdoc" || ((name === "href" || name === "src") && value.startsWith("javascript:"))) {
        element.removeAttribute(attribute.name);
      }
      if (name === "src" && /^https?:/.test(value)) element.removeAttribute(attribute.name);
    }
    if (element instanceof HTMLAnchorElement) {
      element.rel = "noreferrer";
      if (/^https?:/.test(element.href)) element.target = "_blank";
    }
  }
  for (const image of [...root.querySelectorAll("img")]) {
    if (image.getAttribute("src")) continue;
    const description = image.getAttribute("alt")?.trim();
    if (!description) { image.remove(); continue; }
    const figure = document.createElement("span");
    figure.className = "figure-desc";
    figure.textContent = description;
    image.replaceWith(figure);
  }
  return root.innerHTML;
}

export function articleMarkup(html?: string, markdown?: string): string {
  const rendered = html ?? (markdown ? marked.parse(markdown, { async: false }) as string : "<p>Article text is being prepared.</p>");
  return sanitizeArticle(rendered);
}

export function attachWordTimings(root: HTMLElement, words: WordTiming[]): Map<number, HTMLElement> {
  const existing = root.querySelectorAll<HTMLElement>("[data-word-index]");
  if (existing.length) return new Map([...existing].map((element) => [Number(element.dataset.wordIndex), element]));

  const elements: HTMLElement[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || parent.closest("math, svg, [aria-hidden='true']") || !node.textContent?.trim()) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  const wordToken = /^[\p{L}\p{N}_]+(?:[’'\-][\p{L}\p{N}_]+)*$/u;
  for (const node of nodes) {
    const fragment = document.createDocumentFragment();
    for (const token of node.data.split(/([\p{L}\p{N}_]+(?:[’'\-][\p{L}\p{N}_]+)*)/gu)) {
      if (!token || !wordToken.test(token)) { fragment.append(token); continue; }
      const span = document.createElement("span");
      span.className = "spoken-word";
      span.dataset.wordIndex = String(elements.length);
      span.textContent = token;
      elements.push(span);
      fragment.append(span);
    }
    node.replaceWith(fragment);
  }

  const normalize = (value: string): string => value.toLocaleLowerCase().replace(/[^\p{L}\p{N}'’-]+/gu, "");
  const map = new Map<number, HTMLElement>();
  let cursor = 0;
  let previousIndex = 0;
  const maxLookahead = 64;
  const confirmDepth = 2;
  const elementTexts = elements.map((element) => normalize(element.textContent ?? ""));
  const spokenTexts = words.map((word) => typeof word.displayWordId === "string" ? normalize(word.text) : null);
  // A candidate away from the cursor is only trusted when the narration that follows
  // it keeps matching the display run — a lone stopword match (e.g. "a" inside a
  // narration-only figure description) must not drag the cursor across the article.
  const confirmed = (position: number, candidate: number): boolean => {
    let elementCursor = candidate + 1;
    let checks = 0;
    for (let next = position + 1; next < words.length && checks < confirmDepth; next += 1) {
      const target = spokenTexts[next];
      if (target === null || target === undefined) continue;
      const found = elementTexts.slice(elementCursor, elementCursor + 3).indexOf(target);
      if (found < 0) return false;
      elementCursor += found + 1;
      checks += 1;
    }
    return checks > 0;
  };
  for (const [position, word] of words.entries()) {
    let index = position;
    if (word.displayWordId === null) {
      index = previousIndex;
    } else if (word.displayWordId !== undefined) {
      index = previousIndex;
      const target = spokenTexts[position]!;
      const limit = Math.min(elements.length, cursor + maxLookahead + 1);
      for (let candidate = cursor; candidate < limit; candidate += 1) {
        if (elementTexts[candidate] !== target) continue;
        if (candidate !== cursor && !confirmed(position, candidate)) continue;
        index = candidate; cursor = candidate + 1; previousIndex = candidate;
        break;
      }
    }
    word.index = index;
    const element = elements[index];
    if (element) { element.dataset.wordIndex = String(index); map.set(index, element); }
  }
  return map;
}

export function plainArticleText(root: HTMLElement): string {
  return (root.textContent ?? "").replace(/\s+/g, " ").trim();
}
