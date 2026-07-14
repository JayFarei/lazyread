import "./styles.css";
import article from "./generated/article.json";
import { preloadAudio, type AudioManifest } from "./audio";
import { createHighlightController } from "./highlight-controller";
import { findWordAtTime, formatTime, type WordTiming } from "./player";
import {
  createUndoHistory,
  paragraphTarget,
  wordTarget,
  type ParagraphDirection,
  type WordDirection,
} from "./reader-actions";
import { createReadingTracker } from "./reading-tracker";
import { createSpeedMenu } from "./speed-menu";

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("Missing #app element");

const published = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
}).format(new Date(`${article.metadata.published}T12:00:00`));

app.innerHTML = `
  <div class="ambient ambient-one"></div>
  <div class="ambient ambient-two"></div>
  <header class="site-header">
    <a class="brand" href="#top" aria-label="Listening Reader home">
      <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
      <span>Listening Reader</span>
    </a>
    <div class="header-actions">
      <button class="header-control liquid-glass" id="theme-button" type="button" aria-label="Use dark theme">
        <span class="header-icon theme-icon" data-state="moon" aria-hidden="true">
          <svg class="header-glyph" data-icon="moon" viewBox="0 0 24 24" focusable="false">
            <path d="M19.15 15.35A7.7 7.7 0 0 1 8.65 4.85a7.7 7.7 0 1 0 10.5 10.5Z" />
          </svg>
          <svg class="header-glyph" data-icon="sun" viewBox="0 0 24 24" focusable="false">
            <circle cx="12" cy="12" r="3.35" />
            <path d="M12 2.75v2M12 19.25v2M2.75 12h2M19.25 12h2M5.45 5.45l1.4 1.4M17.15 17.15l1.4 1.4M18.55 5.45l-1.4 1.4M6.85 17.15l-1.4 1.4" />
          </svg>
        </span>
      </button>
      <a class="header-control liquid-glass source-link" href="${article.metadata.source}" target="_blank" rel="noreferrer" aria-label="Open original article in a new tab">
        <svg class="header-glyph source-icon" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
          <path d="M7.75 16.25 16.25 7.75M10.25 7.75h6v6" />
        </svg>
      </a>
    </div>
  </header>

  <main id="top">
    <section class="article-hero">
      <p class="eyebrow">${article.metadata.site} · ${published}</p>
      <h1>${article.metadata.title}</h1>
      <p class="dek">${article.metadata.description}</p>
      <div class="article-byline">
        <span>By ${article.metadata.author}</span>
        <span>${article.metadata.wordCount.toLocaleString()} words</span>
        <span id="reading-time">Loading audio…</span>
      </div>
    </section>

    <div class="reader-layout">
      <aside class="rail" aria-label="Article navigation">
        <div class="rail-sticky">
          <p class="rail-label">In this essay</p>
          <nav id="toc"></nav>
          <div class="listen-status">
            <span class="status-dot" id="status-dot"></span>
            <span id="audio-status">Preparing narration</span>
          </div>
        </div>
      </aside>

      <article class="article-body" id="article-body">
        ${article.html}
      </article>
    </div>
  </main>

  <div class="bottom-dock">
    <footer class="player-shell" id="player-shell">
      <div class="player">
        <button class="play-button" id="play-button" type="button" aria-label="Play article" disabled>
          <span class="player-icon" id="play-icon" data-state="play" aria-hidden="true">
            <svg class="playback-glyph playback-glyph--play" data-icon="play" viewBox="0 0 24 24" focusable="false">
              <path d="M8.4 6.72c0-1.06 1.16-1.72 2.08-1.18l9.06 5.28c.91.53.91 1.84 0 2.37l-9.06 5.28c-.92.53-2.08-.13-2.08-1.19V6.72Z" />
            </svg>
            <svg class="playback-glyph playback-glyph--pause" data-icon="pause" viewBox="0 0 24 24" focusable="false">
              <rect x="6.75" y="5" width="4" height="14" rx="1.7" />
              <rect x="13.25" y="5" width="4" height="14" rx="1.7" />
            </svg>
            <svg class="playback-glyph playback-glyph--replay" data-icon="replay" viewBox="0 0 24 24" focusable="false">
              <path d="M5.7 8.25A7.5 7.5 0 1 1 4.5 14" />
              <path d="M5.7 4.75v3.5h3.5" />
            </svg>
          </span>
        </button>

        <div class="player-main">
          <div class="player-meta">
            <div>
              <span class="now-playing">Now reading</span>
              <span class="player-loading-status" id="player-loading-status" aria-live="polite">Preparing narration</span>
              <strong id="current-section">${article.metadata.title}</strong>
            </div>
            <span class="voice-label" id="voice-label">Local narration</span>
          </div>
          <div class="timeline-row">
            <span id="current-time">0:00</span>
            <input id="timeline" type="range" min="0" max="1000" value="0" aria-label="Article progress" disabled />
            <span id="duration">—:——</span>
          </div>
        </div>

        <div class="player-actions">
          <div class="speed-control">
            <button class="speed-button liquid-glass" id="speed-button" type="button" aria-label="Playback speed, 1×" aria-haspopup="listbox" aria-expanded="false" aria-controls="speed-menu">
              <svg class="pace-icon" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                <path d="M4.25 15.15a6.75 6.75 0 0 1 13.5 0H4.25Z" />
                <path d="m8.1 9.35 2.9 5.8 2.9-5.8M6.15 12.15h9.7M17.35 12.2h2.05a1.75 1.75 0 0 1 0 3.5h-1.8M7.1 15.15l-1.25 2M14.9 15.15l1.25 2M4.45 13.3l-1.7-.85" />
                <circle cx="19.85" cy="13.45" r=".5" />
              </svg>
              <span id="speed-value">1×</span>
              <svg class="speed-chevron" viewBox="0 0 20 20" focusable="false" aria-hidden="true">
                <path d="m6.75 8 3.25-3 3.25 3M13.25 12 10 15l-3.25-3" />
              </svg>
            </button>
          </div>

          <button class="highlight-button liquid-glass" id="highlight-button" type="button" aria-label="Open saved highlights" aria-expanded="false" aria-controls="highlight-panel">
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
              <path d="m8.25 14.75 6.5-6.5 2.8 2.8-6.5 6.5H8.25v-2.8Z" />
              <path d="m13.6 9.4 1.75-1.75a1.25 1.25 0 0 1 1.77 0l1.03 1.03a1.25 1.25 0 0 1 0 1.77L16.4 12.2M6.5 19.25h11" />
            </svg>
            <span class="highlight-count" id="highlight-count" hidden>0</span>
          </button>
        </div>
      </div>
    </footer>

    <aside class="shortcut-hud" aria-label="Keyboard shortcuts">
      <span class="shortcut-title">Shortcuts</span>
      <div class="shortcut-grid">
        <span><kbd>H</kbd><small>mark</small></span>
        <span><kbd>⇧ H</kbd><small>prior</small></span>
        <span><kbd>U</kbd><small>undo</small></span>
        <span><kbd>↵</kbd><small>play / pause</small></span>
        <span><kbd>P</kbd><small>next ¶</small></span>
        <span><kbd>⇧ P</kbd><small>prior ¶</small></span>
        <span><kbd>W</kbd><small>next word</small></span>
        <span><kbd>B</kbd><small>prior word</small></span>
      </div>
      <span class="shortcut-status" id="shortcut-status" aria-live="polite"></span>
    </aside>

    <div class="speed-menu liquid-glass" id="speed-menu" role="listbox" aria-label="Playback speed" hidden>
      <button type="button" role="option" data-rate="0.8" aria-selected="false">0.8×</button>
      <button type="button" role="option" data-rate="1" aria-selected="true">1×</button>
      <button type="button" role="option" data-rate="1.15" aria-selected="false">1.15×</button>
      <button type="button" role="option" data-rate="1.3" aria-selected="false">1.3×</button>
      <button type="button" role="option" data-rate="1.5" aria-selected="false">1.5×</button>
      <button type="button" role="option" data-rate="1.75" aria-selected="false">1.75×</button>
      <button type="button" role="option" data-rate="2" aria-selected="false">2×</button>
    </div>

    <section class="highlight-panel liquid-glass" id="highlight-panel" aria-labelledby="highlight-title" hidden>
      <div class="highlight-panel-header">
        <div>
          <span>Reading notes</span>
          <h2 id="highlight-title">Highlights</h2>
        </div>
        <button class="panel-close" id="highlight-close" type="button" aria-label="Close highlights">
          <svg viewBox="0 0 20 20" focusable="false" aria-hidden="true"><path d="m6 6 8 8M14 6l-8 8" /></svg>
        </button>
      </div>
      <p class="highlight-empty" id="highlight-empty">Press <kbd>H</kbd> for the current sentence or <kbd>⇧ H</kbd> for the previous one.</p>
      <ol class="highlight-list" id="highlight-list"></ol>
      <div class="highlight-actions">
        <button id="copy-highlights" type="button" disabled>Copy highlights</button>
        <button class="primary" id="copy-ai" type="button" disabled>Copy for AI</button>
      </div>
      <p class="copy-status" id="copy-status" aria-live="polite"></p>
    </section>
  </div>

  <audio id="audio" preload="auto"></audio>
`;

const required = <T extends Element>(selector: string): T => {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing ${selector}`);
  return element;
};

const audio = required<HTMLAudioElement>("#audio");
const playButton = required<HTMLButtonElement>("#play-button");
const playIcon = required<HTMLElement>("#play-icon");
const timeline = required<HTMLInputElement>("#timeline");
const currentTime = required<HTMLElement>("#current-time");
const duration = required<HTMLElement>("#duration");
const speedButton = required<HTMLButtonElement>("#speed-button");
const speedValue = required<HTMLElement>("#speed-value");
const speedMenu = required<HTMLElement>("#speed-menu");
const status = required<HTMLElement>("#audio-status");
const statusDot = required<HTMLElement>("#status-dot");
const playerLoadingStatus = required<HTMLElement>("#player-loading-status");
const readingTime = required<HTMLElement>("#reading-time");
const voiceLabel = required<HTMLElement>("#voice-label");
const currentSection = required<HTMLElement>("#current-section");
const articleBody = required<HTMLElement>("#article-body");
const themeButton = required<HTMLButtonElement>("#theme-button");
const themeIcon = required<HTMLElement>(".theme-icon");
const shortcutStatus = required<HTMLElement>("#shortcut-status");

let manifest: AudioManifest | null = null;
let activeWord: HTMLElement | null = null;
let activeBlock: HTMLElement | null = null;
let frame = 0;
const readingTracker = createReadingTracker();
const undoHistory = createUndoHistory();

const headings = [...articleBody.querySelectorAll<HTMLHeadingElement>("h2")];
const toc = required<HTMLElement>("#toc");
for (const [index, heading] of headings.entries()) {
  const id = `section-${index + 1}`;
  heading.id = id;
  const link = document.createElement("a");
  link.href = `#${id}`;
  link.textContent = heading.textContent;
  toc.append(link);
}

const paragraphStarts = [
  ...new Set(
    [...articleBody.querySelectorAll<HTMLElement>(".speech-block")]
      .filter((block) => block.matches("p, li, blockquote"))
      .map((block) =>
        Number(
          block.querySelector<HTMLElement>(".spoken-word")?.dataset.wordIndex,
        ),
      )
      .filter(Number.isFinite),
  ),
];

const announceShortcut = (message: string): void => {
  shortcutStatus.textContent = message;
};

let closeSpeedMenu = (): void => {};
const highlightController = createHighlightController({
  articleBody,
  getActiveWord: () => activeWord,
  title: article.metadata.title,
  source: article.metadata.source,
  undoHistory,
  announce: announceShortcut,
  onOpen: () => closeSpeedMenu(),
});
const speedController = createSpeedMenu({
  audio,
  button: speedButton,
  value: speedValue,
  menu: speedMenu,
  onOpen: () => highlightController.close(),
});
closeSpeedMenu = speedController.close;

async function loadAudio(): Promise<void> {
  const response = await fetch("/audio/timings.json", { cache: "no-cache" });
  if (!response.ok) throw new Error("Narration manifest is unavailable");
  manifest = (await response.json()) as AudioManifest;

  duration.textContent = formatTime(manifest.duration);
  readingTime.textContent = `${Math.round(manifest.duration / 60)} min listen`;
  voiceLabel.textContent = `${manifest.voice} · local Qwen3-TTS`;
  await preloadAudio(audio, manifest.audio, (percent) => {
    status.textContent = `Preloading narration · ${Math.round(percent)}%`;
    playerLoadingStatus.textContent = `Loading · ${Math.round(percent)}%`;
  });

  status.textContent = "Narration ready offline";
  playerLoadingStatus.hidden = true;
  statusDot.classList.add("ready");
  playButton.disabled = false;
  timeline.disabled = false;
}

function syncTimelineProgress(): void {
  timeline.style.setProperty("--progress", `${Number(timeline.value) / 10}%`);
}

function updateHighlight(): void {
  if (!manifest) return;
  const timingPosition = findWordAtTime(manifest.words, audio.currentTime);
  const word = timingPosition >= 0 ? manifest.words[timingPosition] : undefined;
  const nextWord = word
    ? articleBody.querySelector<HTMLElement>(`[data-word-index="${word.index}"]`)
    : null;

  if (!nextWord && activeWord) {
    activeWord.classList.remove("is-current");
    activeWord = null;
  }

  if (nextWord && nextWord !== activeWord) {
    activeWord?.classList.remove("is-current");
    activeWord = nextWord;
    activeWord.classList.add("is-current");

    const nextBlock = activeWord.closest<HTMLElement>(".speech-block");
    if (nextBlock !== activeBlock) {
      activeBlock?.classList.remove("is-active");
      activeBlock = nextBlock;
      activeBlock?.classList.add("is-active");

      const nearestHeading = activeBlock
        ? [...articleBody.querySelectorAll<HTMLHeadingElement>("h2")]
            .filter((heading) => heading.compareDocumentPosition(activeBlock!) & Node.DOCUMENT_POSITION_FOLLOWING)
            .at(-1)
        : null;
      currentSection.textContent = nearestHeading?.textContent ?? article.metadata.title;
    }

  }

  readingTracker.track(activeWord, audio.paused);

  currentTime.textContent = formatTime(audio.currentTime);
  timeline.value = String(
    audio.duration ? Math.round((audio.currentTime / audio.duration) * 1000) : 0,
  );
  syncTimelineProgress();

  if (!audio.paused) frame = requestAnimationFrame(updateHighlight);
}

function currentReaderWordIndex(): number {
  const activeIndex = Number(activeWord?.dataset.wordIndex);
  if (Number.isFinite(activeIndex)) return activeIndex;
  if (!manifest) return paragraphStarts[0] ?? 0;
  let latestIndex = manifest.words[0]?.index ?? 0;
  for (const word of manifest.words) {
    if (word.start > audio.currentTime) break;
    latestIndex = word.index;
  }
  return latestIndex;
}

function seekToWord(wordIndex: number, message: string): void {
  if (!manifest) {
    announceShortcut("Narration is still loading");
    return;
  }
  const timing = manifest.words.find((word) => word.index === wordIndex);
  const word = articleBody.querySelector<HTMLElement>(
    `[data-word-index="${wordIndex}"]`,
  );
  if (!timing || !word) return;

  const previousTime = audio.currentTime;
  const previousScroll = document.scrollingElement?.scrollTop ?? 0;
  undoHistory.record(() => {
    audio.currentTime = previousTime;
    updateHighlight();
    document.scrollingElement?.scrollTo({
      top: previousScroll,
      behavior: "smooth",
    });
    announceShortcut("Last navigation undone");
  });

  audio.currentTime = timing.start;
  readingTracker.resume();
  updateHighlight();
  readingTracker.reveal(word);
  announceShortcut(message);
}

function jumpParagraph(direction: ParagraphDirection): void {
  const target = paragraphTarget(
    paragraphStarts,
    currentReaderWordIndex(),
    direction,
  );
  if (target === null) {
    announceShortcut(
      direction === "next"
        ? "Already at the final paragraph"
        : "Already at the first paragraph",
    );
    return;
  }
  seekToWord(
    target,
    direction === "next" ? "Next paragraph" : "Previous paragraph",
  );
}

function jumpWord(direction: WordDirection): void {
  if (!manifest) {
    announceShortcut("Narration is still loading");
    return;
  }
  const target = wordTarget(
    manifest.words.map((word) => word.index),
    currentReaderWordIndex(),
    direction,
  );
  if (target === null) {
    announceShortcut(
      direction === "next"
        ? "Already at the final word"
        : "Already at the first word",
    );
    return;
  }
  seekToWord(target, direction === "next" ? "Next word" : "Previous word");
}

async function togglePlayback(): Promise<void> {
  if (playButton.disabled) {
    announceShortcut("Narration is still loading");
    return;
  }
  if (audio.paused) {
    readingTracker.resume();
    await audio.play();
    announceShortcut("Playback started");
  } else {
    audio.pause();
    announceShortcut("Playback paused");
  }
}

playButton.addEventListener("click", () => {
  void togglePlayback();
});

audio.addEventListener("play", () => {
  readingTracker.start();
  playIcon.dataset.state = "pause";
  playButton.setAttribute("aria-label", "Pause article");
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(updateHighlight);
});

audio.addEventListener("pause", () => {
  readingTracker.stop();
  playIcon.dataset.state = "play";
  playButton.setAttribute("aria-label", "Play article");
  cancelAnimationFrame(frame);
  updateHighlight();
});

audio.addEventListener("ended", () => {
  readingTracker.stop();
  playIcon.dataset.state = "replay";
  playButton.setAttribute("aria-label", "Replay article");
});

timeline.addEventListener("input", () => {
  if (!audio.duration) return;
  audio.currentTime = (Number(timeline.value) / 1000) * audio.duration;
  syncTimelineProgress();
  updateHighlight();
});

articleBody.addEventListener("click", (event) => {
  const target = (event.target as HTMLElement).closest<HTMLElement>(".spoken-word");
  if (!target) return;
  const index = Number(target.dataset.wordIndex);
  seekToWord(index, "Narration moved");
});

const noteManualScroll = (): void => {
  readingTracker.noteManualInteraction();
};
window.addEventListener("wheel", noteManualScroll, { passive: true });
window.addEventListener("touchstart", noteManualScroll, { passive: true });

document.addEventListener("keydown", (event) => {
  const target = event.target as HTMLElement;
  const isEditable =
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target.isContentEditable;
  if (isEditable || event.metaKey || event.ctrlKey || event.altKey) return;

  const isInteractive = Boolean(
    target.closest("button, a, [role='button'], [role='option']"),
  );
  if (event.key === "Enter" && !isInteractive) {
    event.preventDefault();
    void togglePlayback();
    return;
  }

  if (event.key.toLowerCase() === "u") {
    event.preventDefault();
    if (!undoHistory.undo()) announceShortcut("Nothing to undo");
    return;
  }

  if (event.key.toLowerCase() === "p") {
    event.preventDefault();
    jumpParagraph(event.shiftKey ? "previous" : "next");
    return;
  }

  if (event.key.toLowerCase() === "w" || event.key.toLowerCase() === "b") {
    event.preventDefault();
    jumpWord(event.key.toLowerCase() === "w" ? "next" : "previous");
    return;
  }

  if (
    target === document.body &&
    ["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(event.key)
  ) {
    noteManualScroll();
  }
});

themeButton.addEventListener("click", () => {
  const dark = document.documentElement.classList.toggle("dark");
  themeIcon.dataset.state = dark ? "sun" : "moon";
  themeButton.setAttribute("aria-label", dark ? "Use light theme" : "Use dark theme");
});

loadAudio().catch((error: unknown) => {
  console.error(error);
  status.textContent = error instanceof Error ? error.message : "Narration unavailable";
  playerLoadingStatus.textContent = "Narration unavailable";
  statusDot.classList.add("error");
  readingTime.textContent = "Audio unavailable";
});
