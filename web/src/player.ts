import type { Highlight, WordTiming } from "./types";

export function findWordAtTime(words: WordTiming[], time: number): number {
  if (!words.length || time < words[0]!.start) return -1;
  let low = 0;
  let high = words.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (words[middle]!.start <= time) { found = middle; low = middle + 1; }
    else high = middle - 1;
  }
  return found >= 0 && time <= words[found]!.end + 0.18 ? found : -1;
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export type Shortcut =
  | { type: "toggle" }
  | { type: "undo" }
  | { type: "highlight"; previous: boolean }
  | { type: "paragraph"; direction: "next" | "previous" }
  | { type: "word"; direction: "next" | "previous" };

export function getShortcut(event: KeyboardEvent): Shortcut | null {
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  const key = event.key.toLowerCase();
  if (event.key === "Enter") return { type: "toggle" };
  if (key === "u") return { type: "undo" };
  if (key === "h") return { type: "highlight", previous: event.shiftKey };
  if (key === "p") return { type: "paragraph", direction: event.shiftKey ? "previous" : "next" };
  if (key === "w") return { type: "word", direction: "next" };
  if (key === "b") return { type: "word", direction: "previous" };
  return null;
}

export function sentenceRanges(words: WordTiming[]): Highlight[] {
  const result: Highlight[] = [];
  let start = 0;
  for (const [position, word] of words.entries()) {
    const closes = /[.!?][\]})"'’”]*$/.test(word.text);
    if (!closes && position < words.length - 1) continue;
    const slice = words.slice(start, position + 1);
    if (slice.length) result.push({
      id: `${slice[0]!.index}-${slice.at(-1)!.index}`,
      text: slice.map((item) => item.text).join(" "),
      startIndex: slice[0]!.index,
      endIndex: slice.at(-1)!.index,
    });
    start = position + 1;
  }
  return result;
}

export function sentenceAt(ranges: Highlight[], wordIndex: number, previous = false): Highlight | null {
  const current = ranges.findIndex((range) => wordIndex >= range.startIndex && wordIndex <= range.endIndex);
  return ranges[previous ? current - 1 : current] ?? null;
}

export function toggleHighlight(highlights: Highlight[], next: Highlight): Highlight[] {
  return highlights.some((item) => item.id === next.id)
    ? highlights.filter((item) => item.id !== next.id)
    : [...highlights, next];
}

export function adjacentIndex(indexes: number[], current: number, direction: "next" | "previous"): number | null {
  let position = -1;
  for (const [candidatePosition, value] of indexes.entries()) {
    if (value > current) break;
    position = candidatePosition;
  }
  return indexes[direction === "next" ? position + 1 : position - 1] ?? null;
}
