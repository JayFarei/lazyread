import { describe, expect, it } from "vitest";
import { createUndoHistory, paragraphTarget, wordTarget } from "./reader-actions";

describe("paragraphTarget", () => {
  it("moves to the first word of the next or previous speech block", () => {
    const paragraphStarts = [0, 10, 20, 35];

    expect(paragraphTarget(paragraphStarts, 14, "next")).toBe(20);
    expect(paragraphTarget(paragraphStarts, 14, "previous")).toBe(0);
    expect(paragraphTarget(paragraphStarts, 0, "previous")).toBeNull();
    expect(paragraphTarget(paragraphStarts, 38, "next")).toBeNull();
  });
});

describe("createUndoHistory", () => {
  it("undoes reader actions in reverse order", () => {
    let position = 0;
    const history = createUndoHistory();

    position = 12;
    history.record(() => {
      position = 0;
    });
    position = 28;
    history.record(() => {
      position = 12;
    });

    expect(history.undo()).toBe(true);
    expect(position).toBe(12);
    expect(history.undo()).toBe(true);
    expect(position).toBe(0);
    expect(history.undo()).toBe(false);
  });
});

describe("wordTarget", () => {
  it("moves to the adjacent spoken word without assuming contiguous indexes", () => {
    const wordIndexes = [4, 7, 11, 18];

    expect(wordTarget(wordIndexes, 7, "next")).toBe(11);
    expect(wordTarget(wordIndexes, 11, "previous")).toBe(7);
    expect(wordTarget(wordIndexes, 4, "previous")).toBeNull();
    expect(wordTarget(wordIndexes, 18, "next")).toBeNull();
  });
});
