import {
  buildAiExport,
  sentenceForWord,
  sentencesFromBlock,
  type ReaderSentence,
  type SentenceDirection,
  type WordOffset,
} from "./highlights";
import type { UndoHistory } from "./reader-actions";

export type HighlightController = {
  close: () => void;
};

const required = <T extends Element>(selector: string): T => {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing ${selector}`);
  return element;
};

export function createHighlightController(input: {
  articleBody: HTMLElement;
  getActiveWord: () => HTMLElement | null;
  title: string;
  source: string;
  undoHistory: UndoHistory;
  announce: (message: string) => void;
  onOpen: () => void;
}): HighlightController {
  const button = required<HTMLButtonElement>("#highlight-button");
  const count = required<HTMLElement>("#highlight-count");
  const panel = required<HTMLElement>("#highlight-panel");
  const closeButton = required<HTMLButtonElement>("#highlight-close");
  const empty = required<HTMLElement>("#highlight-empty");
  const list = required<HTMLOListElement>("#highlight-list");
  const copyHighlights = required<HTMLButtonElement>("#copy-highlights");
  const copyAi = required<HTMLButtonElement>("#copy-ai");
  const copyStatus = required<HTMLElement>("#copy-status");
  const wordElements = [
    ...input.articleBody.querySelectorAll<HTMLElement>(".spoken-word"),
  ];
  const wordsByIndex = new Map(
    wordElements.map((word) => [Number(word.dataset.wordIndex), word]),
  );
  const savedHighlights = new Map<string, ReaderSentence>();

  const sentences = [
    ...input.articleBody.querySelectorAll<HTMLElement>(".speech-block"),
  ].flatMap((block, blockIndex) => {
    const offsets: WordOffset[] = [];
    const seenWords = new Set<number>();
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    let cursor = 0;
    let node = walker.nextNode();

    while (node) {
      const text = node.textContent ?? "";
      const word = node.parentElement?.closest<HTMLElement>(".spoken-word");
      const index = Number(word?.dataset.wordIndex);
      if (word && Number.isFinite(index) && !seenWords.has(index)) {
        offsets.push({ index, start: cursor, end: cursor + text.length });
        seenWords.add(index);
      }
      cursor += text.length;
      node = walker.nextNode();
    }

    return sentencesFromBlock(block.textContent ?? "", offsets, blockIndex);
  });
  const flattenedArticle = (input.articleBody.textContent ?? "")
    .replace(/\s+/g, " ")
    .trim();

  const setPanel = (open: boolean, restoreFocus = false): void => {
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    if (open) {
      input.onOpen();
      closeButton.focus({ preventScroll: true });
    } else if (restoreFocus) button.focus({ preventScroll: true });
  };

  const currentReadingWordIndex = (): number | null => {
    const activeIndex = Number(input.getActiveWord()?.dataset.wordIndex);
    if (Number.isFinite(activeIndex)) return activeIndex;

    const readingLine = window.innerHeight * 0.25;
    let nearest: { distance: number; index: number } | null = null;
    for (const word of wordElements) {
      const rect = word.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
      const index = Number(word.dataset.wordIndex);
      const distance = Math.abs(rect.top - readingLine);
      if (!nearest || distance < nearest.distance) nearest = { distance, index };
    }
    return nearest?.index ?? null;
  };

  const render = (): void => {
    const highlights = [...savedHighlights.values()];
    list.replaceChildren();
    empty.hidden = highlights.length > 0;
    count.hidden = highlights.length === 0;
    count.textContent = String(highlights.length);
    copyHighlights.disabled = highlights.length === 0;
    copyAi.disabled = highlights.length === 0;

    for (const sentence of highlights) {
      const item = document.createElement("li");
      const text = document.createElement("p");
      text.textContent = sentence.text;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove highlight: ${sentence.text}`);
      remove.innerHTML =
        '<svg viewBox="0 0 20 20" focusable="false" aria-hidden="true"><path d="m6 6 8 8M14 6l-8 8" /></svg>';
      remove.addEventListener("click", () => {
        savedHighlights.delete(sentence.id);
        for (const index of sentence.wordIndexes) {
          wordsByIndex.get(index)?.classList.remove("is-saved");
        }
        input.undoHistory.record(() => {
          savedHighlights.set(sentence.id, sentence);
          for (const index of sentence.wordIndexes) {
            wordsByIndex.get(index)?.classList.add("is-saved");
          }
          copyStatus.textContent = "Highlight removal undone.";
          input.announce("Highlight removal undone");
          render();
        });
        copyStatus.textContent = "Highlight removed.";
        input.announce("Highlight removed");
        render();
      });
      item.append(text, remove);
      list.append(item);
    }
  };

  const toggleSentence = (direction: SentenceDirection): void => {
    const wordIndex = currentReadingWordIndex();
    const sentence =
      wordIndex === null ? null : sentenceForWord(sentences, wordIndex, direction);
    if (!sentence) {
      copyStatus.textContent =
        direction === "previous"
          ? "There is no previous sentence here."
          : "No sentence is currently in the reading position.";
      return;
    }

    const isSaved = savedHighlights.has(sentence.id);
    if (isSaved) savedHighlights.delete(sentence.id);
    else savedHighlights.set(sentence.id, sentence);
    for (const index of sentence.wordIndexes) {
      wordsByIndex.get(index)?.classList.toggle("is-saved", !isSaved);
    }
    input.undoHistory.record(() => {
      if (isSaved) savedHighlights.set(sentence.id, sentence);
      else savedHighlights.delete(sentence.id);
      for (const index of sentence.wordIndexes) {
        wordsByIndex.get(index)?.classList.toggle("is-saved", isSaved);
      }
      copyStatus.textContent = "Highlight action undone.";
      input.announce("Highlight action undone");
      render();
    });
    copyStatus.textContent = isSaved ? "Highlight removed." : "Sentence highlighted.";
    input.announce(isSaved ? "Highlight removed" : "Sentence highlighted");
    render();
  };

  const writeClipboard = async (text: string, message: string): Promise<void> => {
    await navigator.clipboard.writeText(text);
    copyStatus.textContent = message;
  };

  button.addEventListener("click", () => setPanel(panel.hidden));
  closeButton.addEventListener("click", () => setPanel(false, true));
  copyHighlights.addEventListener("click", () => {
    const text = [...savedHighlights.values()]
      .map((sentence) => sentence.text)
      .join("\n\n");
    void writeClipboard(text, "Highlights copied.").catch(() => {
      copyStatus.textContent = "Clipboard access is unavailable.";
    });
  });
  copyAi.addEventListener("click", () => {
    const text = buildAiExport({
      title: input.title,
      source: input.source,
      highlights: [...savedHighlights.values()].map((sentence) => sentence.text),
      articleText: flattenedArticle,
    });
    void writeClipboard(text, "Highlights and flattened article copied for AI.").catch(
      () => {
        copyStatus.textContent = "Clipboard access is unavailable.";
      },
    );
  });

  document.addEventListener("pointerdown", (event) => {
    const target = event.target as Node;
    if (!panel.hidden && !panel.contains(target) && !button.contains(target)) {
      setPanel(false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      setPanel(false, true);
      return;
    }

    const target = event.target as HTMLElement;
    const isEditable =
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement ||
      target.isContentEditable;
    if (isEditable || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key.toLowerCase() !== "h") return;
    event.preventDefault();
    toggleSentence(event.shiftKey ? "previous" : "current");
  });

  render();
  return { close: () => setPanel(false) };
}
