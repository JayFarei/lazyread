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
    }
    if (element instanceof HTMLAnchorElement) {
      element.rel = "noreferrer";
      if (/^https?:/.test(element.href)) element.target = "_blank";
    }
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

  const map = new Map<number, HTMLElement>();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || parent.closest("pre, code, math, svg, [aria-hidden='true']") || !node.textContent?.trim()) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  let position = 0;
  for (const node of nodes) {
    const fragment = document.createDocumentFragment();
    for (const token of node.data.split(/(\s+)/)) {
      if (!token || /^\s+$/.test(token) || !words[position]) { fragment.append(token); continue; }
      const span = document.createElement("span");
      span.className = "spoken-word";
      span.dataset.wordIndex = String(words[position]!.index);
      span.textContent = token;
      map.set(words[position]!.index, span);
      position += 1;
      fragment.append(span);
    }
    node.replaceWith(fragment);
    if (position >= words.length) break;
  }
  return map;
}

export function plainArticleText(root: HTMLElement): string {
  return (root.textContent ?? "").replace(/\s+/g, " ").trim();
}
