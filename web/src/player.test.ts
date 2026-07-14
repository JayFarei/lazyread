// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { findWordAtTime, getShortcut, sentenceRanges, toggleHighlight } from "./player";

const words = [
  { index: 0, text: "One", start: 0, end: 0.4 },
  { index: 1, text: "sentence.", start: 0.5, end: 1 },
  { index: 2, text: "Two", start: 1.2, end: 1.5 },
  { index: 3, text: "more!", start: 1.6, end: 2 },
];

describe("player seams", () => {
  it("finds the latest word at a playback time", () => {
    expect(findWordAtTime(words, 0.55)).toBe(1);
    expect(findWordAtTime(words, 1.19)).toBe(-1);
  });

  it("maps navigation and playback keys without claiming Space", () => {
    expect(getShortcut(new KeyboardEvent("keydown", { key: "Enter" }))).toEqual({ type: "toggle" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: "P", shiftKey: true }))).toEqual({ type: "paragraph", direction: "previous" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: "w" }))).toEqual({ type: "word", direction: "next" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: " " }))).toBeNull();
  });

  it("derives sentence highlights and toggles them", () => {
    const ranges = sentenceRanges(words);
    expect(ranges.map((range) => range.text)).toEqual(["One sentence.", "Two more!"]);
    expect(toggleHighlight([], ranges[0]!)).toHaveLength(1);
    expect(toggleHighlight([ranges[0]!], ranges[0]!)).toHaveLength(0);
  });
});
