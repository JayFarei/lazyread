import { describe, expect, it } from "vitest";
import { findWordAtTime, formatTime, type WordTiming } from "./player";

const words: WordTiming[] = [
  { index: 0, text: "The", start: 0.2, end: 0.4 },
  { index: 1, text: "future", start: 0.42, end: 0.8 },
  { index: 2, text: "human", start: 1.0, end: 1.4 },
];

describe("findWordAtTime", () => {
  it("returns the latest word whose start time has passed", () => {
    expect(findWordAtTime(words, 0.3)).toBe(0);
    expect(findWordAtTime(words, 0.7)).toBe(1);
    expect(findWordAtTime(words, 1.2)).toBe(2);
  });

  it("returns -1 before narration begins", () => {
    expect(findWordAtTime(words, 0.1)).toBe(-1);
  });

  it("clears the highlight during longer pauses and after narration", () => {
    expect(findWordAtTime(words, 0.99)).toBe(-1);
    expect(findWordAtTime(words, 1.7)).toBe(-1);
  });
});

describe("formatTime", () => {
  it("formats minutes and padded seconds", () => {
    expect(formatTime(65.9)).toBe("1:05");
    expect(formatTime(Number.NaN)).toBe("0:00");
  });
});
