// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { findWordAtTime, getShortcut, lastWordStartedBefore, sentenceRanges, shouldHandleShortcut, toggleHighlight } from "./player";

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

  it("anchors to the last started word inside a silence gap", () => {
    expect(lastWordStartedBefore(words, 1.19)).toBe(1);
    expect(lastWordStartedBefore(words, 5)).toBe(3);
    expect(lastWordStartedBefore(words, -0.1)).toBe(-1);
  });

  it("maps navigation and playback keys without claiming Space", () => {
    expect(getShortcut(new KeyboardEvent("keydown", { key: "Enter" }))).toEqual({ type: "toggle" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: "P", shiftKey: true }))).toEqual({ type: "paragraph", direction: "previous" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: "w" }))).toEqual({ type: "word", direction: "next" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: "s" }))).toEqual({ type: "speed", direction: "up" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: "S", shiftKey: true }))).toEqual({ type: "speed", direction: "down" });
    expect(getShortcut(new KeyboardEvent("keydown", { key: " " }))).toBeNull();
  });

  it("keeps letter shortcuts active on controls without claiming their native Enter", () => {
    const button = document.createElement("button");
    const link = document.createElement("a");
    const input = document.createElement("input");
    const editor = document.createElement("div");
    editor.setAttribute("contenteditable", "true");
    document.body.append(button, link, input, editor);

    const eventFrom = (target: HTMLElement, key: string): KeyboardEvent => {
      const event = new KeyboardEvent("keydown", { key, bubbles: true });
      target.dispatchEvent(event);
      return event;
    };

    const buttonWord = eventFrom(button, "w");
    const buttonToggle = eventFrom(button, "Enter");
    const linkHighlight = eventFrom(link, "h");
    const inputWord = eventFrom(input, "w");
    const editorWord = eventFrom(editor, "w");

    expect(shouldHandleShortcut(buttonWord, getShortcut(buttonWord)!)).toBe(true);
    expect(shouldHandleShortcut(buttonToggle, getShortcut(buttonToggle)!)).toBe(false);
    expect(shouldHandleShortcut(linkHighlight, getShortcut(linkHighlight)!)).toBe(true);
    expect(shouldHandleShortcut(inputWord, getShortcut(inputWord)!)).toBe(false);
    expect(shouldHandleShortcut(editorWord, getShortcut(editorWord)!)).toBe(false);
  });

  it("derives sentence highlights and toggles them", () => {
    const ranges = sentenceRanges(words);
    expect(ranges.map((range) => range.text)).toEqual(["One sentence.", "Two more!"]);
    expect(toggleHighlight([], ranges[0]!)).toHaveLength(1);
    expect(toggleHighlight([ranges[0]!], ranges[0]!)).toHaveLength(0);
  });

  it("uses projection boundaries when aligned timing words omit punctuation", () => {
    const projected = [
      { index: 0, text: "First", start: 0, end: 0.3 },
      { index: 1, text: "thought", start: 0.3, end: 0.7, sentenceEnd: true, sentenceSuffix: "." },
      { index: 2, text: "Next", start: 0.8, end: 1.1 },
      { index: 3, text: "line", start: 1.1, end: 1.4, sentenceEnd: true },
    ];

    expect(sentenceRanges(projected).map((range) => range.text)).toEqual([
      "First thought.",
      "Next line",
    ]);
  });
});
