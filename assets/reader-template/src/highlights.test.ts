import { describe, expect, it } from "vitest";
import {
  buildAiExport,
  sentenceForWord,
  sentencesFromBlock,
  type ReaderSentence,
  type WordOffset,
} from "./highlights";

describe("sentencesFromBlock", () => {
  it("maps period-delimited sentences and a final line to their spoken words", () => {
    const words: WordOffset[] = [
      { index: 0, start: 0, end: 5 },
      { index: 1, start: 6, end: 14 },
      { index: 2, start: 16, end: 22 },
      { index: 3, start: 23, end: 31 },
      { index: 4, start: 33, end: 38 },
      { index: 5, start: 39, end: 43 },
    ];

    expect(
      sentencesFromBlock("First sentence. Second sentence. Final line", words, 4),
    ).toEqual([
      { id: "block-4-sentence-0", text: "First sentence.", wordIndexes: [0, 1] },
      { id: "block-4-sentence-1", text: "Second sentence.", wordIndexes: [2, 3] },
      { id: "block-4-sentence-2", text: "Final line", wordIndexes: [4, 5] },
    ]);
  });
});

describe("buildAiExport", () => {
  it("combines selected sentences with source context and flattened article text", () => {
    expect(
      buildAiExport({
        title: "The Future Worth Building Is Human",
        source: "https://example.com/article",
        highlights: ["First sentence.", "Second sentence."],
        articleText: "First sentence. Second sentence. Final line",
      }),
    ).toBe(`# Highlights from The Future Worth Building Is Human

Source: https://example.com/article

## Selected passages

- First sentence.
- Second sentence.

## Flattened article

First sentence. Second sentence. Final line`);
  });
});

describe("sentenceForWord", () => {
  it("returns the current sentence or the previous sentence for Shift+H", () => {
    const sentences: ReaderSentence[] = [
      { id: "first", text: "First sentence.", wordIndexes: [0, 1] },
      { id: "second", text: "Second sentence.", wordIndexes: [2, 3] },
    ];

    expect(sentenceForWord(sentences, 3, "current")?.id).toBe("second");
    expect(sentenceForWord(sentences, 3, "previous")?.id).toBe("first");
    expect(sentenceForWord(sentences, 0, "previous")).toBeNull();
  });
});
