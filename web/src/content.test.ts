// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { attachWordTimings, sanitizeArticle } from "./content";

describe("sanitizeArticle", () => {
  it("turns remote images into visible figure descriptions", () => {
    const html = sanitizeArticle(`<p><img src="https://example.com/pic.png" alt="A person at a fork in the road."></p>`);
    expect(html).not.toContain("<img");
    expect(html).toContain(`class="figure-desc"`);
    expect(html).toContain("A person at a fork in the road.");
  });

  it("drops remote images without a description and keeps local ones", () => {
    expect(sanitizeArticle(`<p><img src="https://example.com/pic.png" alt=""></p>`)).toBe("<p></p>");
    expect(sanitizeArticle(`<p><img src="/assets/pic.png" alt="Local figure"></p>`)).toContain("<img");
  });
});

describe("attachWordTimings", () => {
  it("keeps display alignment when speech omits or inserts words", () => {
    document.body.innerHTML = `<article id="body"><h1 hidden>A title</h1><p>Read citation 12 and continue.</p></article>`;
    const root = document.querySelector<HTMLElement>("#body")!;
    const words = [
      { index: 0, text: "A", start: 0, end: 0.1, displayWordId: "dw-a" },
      { index: 1, text: "title", start: 0.1, end: 0.2, displayWordId: "dw-title" },
      { index: 2, text: "Read", start: 0.2, end: 0.3, displayWordId: "dw-read" },
      { index: 3, text: "citation", start: 0.3, end: 0.4, displayWordId: "dw-citation" },
      { index: 4, text: "a", start: 0.4, end: 0.5, displayWordId: null },
      { index: 5, text: "description", start: 0.5, end: 0.6, displayWordId: null },
      { index: 6, text: "and", start: 0.6, end: 0.7, displayWordId: "dw-and" },
      { index: 7, text: "continue", start: 0.7, end: 0.8, displayWordId: "dw-continue" },
    ];

    const map = attachWordTimings(root, words);

    expect(words.map((word) => word.index)).toEqual([0, 1, 2, 3, 3, 3, 5, 6]);
    expect(map.get(5)?.textContent).toBe("and");
    expect(map.get(6)?.textContent).toBe("continue");
  });

  it("keeps inline code words in sequence instead of jumping to a late duplicate", () => {
    document.body.innerHTML = `<article id="body"><p>Start <code>kb/br/97-trace.md</code>.</p><h2>First section</h2><p>Much later: kb.</p></article>`;
    const root = document.querySelector<HTMLElement>("#body")!;
    const words = ["Start", "kb", "br", "97-trace", "md", "First", "section"].map((text, index) => ({
      index,
      text,
      start: index,
      end: index + 0.5,
      displayWordId: `dw-${index}`,
    }));

    const map = attachWordTimings(root, words);

    expect(words.map((word) => word.index)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(map.get(1)?.textContent).toBe("kb");
    expect(map.get(3)?.textContent).toBe("97-trace");
    expect(map.get(5)?.textContent).toBe("First");
  });

  it("does not jump across the article when one projected word is absent", () => {
    const filler = Array.from({ length: 80 }, (_, index) => `filler${index}`).join(" ");
    document.body.innerHTML = `<article id="body"><p>Start Recovery ${filler} absent</p></article>`;
    const root = document.querySelector<HTMLElement>("#body")!;
    const words = [
      { index: 0, text: "Start", start: 0, end: 0.5, displayWordId: "dw-start" },
      { index: 1, text: "absent", start: 0.5, end: 1, displayWordId: "dw-absent" },
      { index: 2, text: "Recovery", start: 1, end: 1.5, displayWordId: "dw-recovery" },
    ];

    const map = attachWordTimings(root, words);

    expect(words.map((word) => word.index)).toEqual([0, 0, 1]);
    expect(map.get(1)?.textContent).toBe("Recovery");
  });

  it("does not let a narrated figure description drag the cursor across later paragraphs", () => {
    // Narration speaks alt text that has no DOM counterpart; its stopwords ("a",
    // "path") also appear in later paragraphs and must not be matched there.
    document.body.innerHTML = `<article id="body"><p>Normal Technology</p><p>The choice is a practical path forward and it continues.</p></article>`;
    const root = document.querySelector<HTMLElement>("#body")!;
    const alt = ["A", "person", "stands", "where", "a", "path", "divides"];
    const words = [
      { index: 0, text: "Normal", start: 0, end: 0.5, displayWordId: "dw-0" },
      { index: 1, text: "Technology", start: 0.5, end: 1, displayWordId: "dw-1" },
      ...alt.map((text, position) => ({ index: 2 + position, text, start: 1 + position, end: 1.5 + position, displayWordId: `dw-alt-${position}` })),
      { index: 9, text: "The", start: 9, end: 9.5, displayWordId: "dw-9" },
      { index: 10, text: "choice", start: 9.5, end: 10, displayWordId: "dw-10" },
      { index: 11, text: "is", start: 10, end: 10.5, displayWordId: "dw-11" },
    ];

    attachWordTimings(root, words);

    // Alt-text words all collapse onto the last real display word instead of
    // stealing "a"/"path" from the following paragraph.
    expect(words.map((word) => word.index)).toEqual([0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 4]);
  });

  it("aligns narrated figure descriptions to their rendered figure card", () => {
    document.body.innerHTML = `<article id="body"><p>Before figure</p><p><span class="figure-desc">A person stands</span></p><p>After it</p></article>`;
    const root = document.querySelector<HTMLElement>("#body")!;
    const words = ["Before", "figure", "A", "person", "stands", "After", "it"].map((text, index) => ({
      index,
      text,
      start: index,
      end: index + 0.5,
      displayWordId: `dw-${index}`,
    }));

    const map = attachWordTimings(root, words);

    expect(words.map((word) => word.index)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(map.get(3)?.textContent).toBe("person");
    expect(map.get(5)?.textContent).toBe("After");
  });
});
