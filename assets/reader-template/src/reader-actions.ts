export type ParagraphDirection = "next" | "previous";
export type WordDirection = "next" | "previous";

export type UndoHistory = {
  record: (undo: () => void) => void;
  undo: () => boolean;
};

function adjacentTarget(
  indexes: number[],
  currentIndex: number,
  direction: "next" | "previous",
): number | null {
  let currentPosition = -1;
  for (const [position, index] of indexes.entries()) {
    if (index > currentIndex) break;
    currentPosition = position;
  }
  const targetPosition =
    direction === "next" ? currentPosition + 1 : currentPosition - 1;
  return indexes[targetPosition] ?? null;
}

export function paragraphTarget(
  paragraphStarts: number[],
  currentWordIndex: number,
  direction: ParagraphDirection,
): number | null {
  return adjacentTarget(paragraphStarts, currentWordIndex, direction);
}

export function createUndoHistory(limit = 50): UndoHistory {
  const actions: Array<() => void> = [];

  return {
    record(undo) {
      actions.push(undo);
      if (actions.length > limit) actions.shift();
    },
    undo() {
      const action = actions.pop();
      if (!action) return false;
      action();
      return true;
    },
  };
}

export function wordTarget(
  wordIndexes: number[],
  currentWordIndex: number,
  direction: WordDirection,
): number | null {
  return adjacentTarget(wordIndexes, currentWordIndex, direction);
}
