export type WordOffset = {
  index: number;
  start: number;
  end: number;
};

export type ReaderSentence = {
  id: string;
  text: string;
  wordIndexes: number[];
};

export type SentenceDirection = "current" | "previous";

export function sentencesFromBlock(
  blockText: string,
  words: WordOffset[],
  blockIndex: number,
): ReaderSentence[] {
  const sentences: ReaderSentence[] = [];
  const sentencePattern = /[^.!?]+(?:[.!?]+(?:["”’')\]]*)|$)/g;

  for (const match of blockText.matchAll(sentencePattern)) {
    const raw = match[0];
    const text = raw.trim();
    if (!text) continue;

    const leadingSpace = raw.length - raw.trimStart().length;
    const start = (match.index ?? 0) + leadingSpace;
    const end = start + text.length;
    const wordIndexes = words
      .filter((word) => word.start < end && word.end > start)
      .map((word) => word.index);

    if (wordIndexes.length === 0) continue;
    sentences.push({
      id: `block-${blockIndex}-sentence-${sentences.length}`,
      text,
      wordIndexes,
    });
  }

  return sentences;
}

export function sentenceForWord(
  sentences: ReaderSentence[],
  wordIndex: number,
  direction: SentenceDirection,
): ReaderSentence | null {
  const currentIndex = sentences.findIndex((sentence) =>
    sentence.wordIndexes.includes(wordIndex),
  );
  if (currentIndex < 0) return null;
  return sentences[direction === "previous" ? currentIndex - 1 : currentIndex] ?? null;
}

export function buildAiExport(input: {
  title: string;
  source: string;
  highlights: string[];
  articleText: string;
}): string {
  const passages = input.highlights.map((highlight) => `- ${highlight}`).join("\n");
  return `# Highlights from ${input.title}

Source: ${input.source}

## Selected passages

${passages}

## Flattened article

${input.articleText}`;
}
