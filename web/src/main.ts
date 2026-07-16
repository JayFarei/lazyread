import "./styles.css";
import { ApiClient, ProgressStream, normalizeManifest } from "./api";
import { preloadCompleteAudio } from "./audio-cache";
import { articleMarkup, attachWordTimings, plainArticleText } from "./content";
import { CleanupScope } from "./lifecycle";
import { initLiquidGlass } from "./liquid-glass";
import { LibraryProgressStreams, newArticleDialogMarkup } from "./library";
import { adjacentIndex, findWordAtTime, formatTime, getShortcut, lastWordStartedBefore, sentenceAt, sentenceRanges, shouldHandleShortcut, toggleHighlight } from "./player";
import { createReadingTracker } from "./reading-tracker";
import { migratedStorageValue } from "./storage";
import type { Article, AudioManifest, Highlight } from "./types";

const api = new ApiClient();
const app = document.querySelector<HTMLDivElement>("#app")!;
if (!app) throw new Error("Missing app root");

let routeScope = new CleanupScope();
const escape = (value = ""): string => value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!);
// Icon path data from Lucide (https://lucide.dev, ISC license); see THIRD_PARTY_NOTICES.md.
const icon = (name: "library" | "sun" | "moon" | "source" | "play" | "pause" | "highlights" | "speed" | "close" | "trash" | "restore" | "retry"): string => {
  const paths = {
    library: '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    source: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    play: '<path class="fill" d="M8 5.3c0-1 1.1-1.6 2-1.1l10.1 6.2c.8.5.8 1.7 0 2.2L10 18.8c-.9.5-2-.1-2-1.1Z"/>',
    pause: '<rect class="fill" x="5.5" y="4" width="5" height="16" rx="1.8"/><rect class="fill" x="13.5" y="4" width="5" height="16" rx="1.8"/>',
    highlights: '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4l8 8Z"/>',
    speed: '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    close: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    restore: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    retry: '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
};

const brandMark = `<span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32">
  <defs>
    <linearGradient id="brand-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3f987a"/><stop offset="1" stop-color="#1c503e"/></linearGradient>
    <linearGradient id="brand-gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="rgba(255,255,255,.42)"/><stop offset="1" stop-color="rgba(255,255,255,0)"/></linearGradient>
    <clipPath id="brand-clip"><rect x="1" y="1" width="30" height="30" rx="10"/></clipPath>
  </defs>
  <rect x="1" y="1" width="30" height="30" rx="10" fill="url(#brand-fill)"/>
  <g clip-path="url(#brand-clip)"><ellipse cx="16" cy="-2" rx="19" ry="12" fill="url(#brand-gloss)"/></g>
  <rect x="1.6" y="1.6" width="28.8" height="28.8" rx="9.4" fill="none" stroke="rgba(255,255,255,.38)" stroke-width="1.1"/>
  <path d="M9.2 19.5v-5M13.7 22.5V9.5M18.3 21v-8M22.8 18.5v-3" stroke="#f4f1e8" stroke-width="2.5" stroke-linecap="round"/>
</svg></span>`;

function shell(content: string, active: "library" | "reader"): string {
  return `<div class="ambient ambient-a"></div><div class="ambient ambient-b"></div>
    <header class="site-header">
      <a class="brand" href="/library" data-link>${brandMark}<span>Lazyread</span></a>
      <nav class="header-actions" aria-label="Site controls">
        ${active === "reader" ? `<a class="round-control liquid" href="/library" data-link aria-label="Open library">${icon("library")}</a>` : ""}
        <button class="round-control liquid" id="theme-toggle" type="button" aria-label="Use dark theme">${icon(document.documentElement.classList.contains("dark") ? "sun" : "moon")}</button>
      </nav>
    </header>${content}`;
}

function setupShell(): void {
  document.querySelector("#theme-toggle")?.addEventListener("click", () => {
    const dark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("lazyread-theme", dark ? "dark" : "light");
    const button = document.querySelector<HTMLButtonElement>("#theme-toggle");
    if (button) { button.innerHTML = icon(dark ? "sun" : "moon"); button.ariaLabel = dark ? "Use light theme" : "Use dark theme"; }
  });
}

function setRoute(path: string): void {
  history.pushState({}, "", path);
  void route();
}

function bindLinks(): void {
  document.querySelectorAll<HTMLAnchorElement>("a[data-link]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    setRoute(new URL(link.href).pathname);
  }));
}

const date = (value?: string): string => value ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)) : "—";
const size = (value?: number): string => value === undefined ? "—" : value > 1e9 ? `${(value / 1e9).toFixed(1)} GB` : `${(value / 1e6).toFixed(value > 1e8 ? 0 : 1)} MB`;
const statusLabel = (article: Article): string => article.status === "processing" ? (article.phase ?? "Preparing") : article.status;

function articleCard(article: Article): string {
  const progress = article.progress;
  const action = article.status === "trashed" ? "restore" : article.status === "failed" ? "retry" : "trash";
  const href = article.route || `/read/${article.id}`;
  return `<article class="library-card status-${article.status}" data-id="${escape(article.id)}">
    <a class="card-main" href="${escape(href)}" data-link>
      <div class="card-status"><span class="status-dot"></span>${escape(statusLabel(article))}</div>
      <h3>${escape(article.title)}</h3>
      <p>${escape(article.description ?? article.sourceUrl ?? (article.status === "failed" ? article.error : "Local listening article") ?? "")}</p>
      ${progress ? `<div class="job-progress" aria-label="${Math.round(progress.percent)} percent"><i style="width:${Math.max(0, Math.min(100, progress.percent))}%"></i></div><small>${Math.round(progress.percent)}%${progress.etaSeconds ? ` · ${formatTime(progress.etaSeconds)} remaining` : ""}</small>` : ""}
      <footer><span>${date(article.createdAt)}</span><span>${article.wordCount?.toLocaleString() ?? "—"} words</span><span>${article.durationSeconds ? `${Math.round(article.durationSeconds / 60)} min` : "Text ready"}</span></footer>
    </a>
    <button class="card-action" data-action="${action}" aria-label="${action} ${escape(article.title)}">${icon(action)}</button>
  </article>`;
}

async function renderLibrary(scope: CleanupScope): Promise<void> {
  document.title = "Library · Lazyread";
  app.innerHTML = shell(`<main class="library-page">
    <section class="library-hero"><div><p class="eyebrow">Your private listening library</p><h1>Read with your ears.</h1><p>Articles become readable first. Natural local narration follows in the background.</p></div><button class="primary-button" id="new-article" type="button">New article</button></section>
    <section class="library-toolbar"><label><span>Search library</span><input id="library-search" type="search" placeholder="Title, author or source" /></label><label><span>Sort</span><select id="library-sort"><option value="recent">Most recent</option><option value="title">Title</option><option value="source">Source</option></select></label></section>
    <div id="library-content" aria-live="polite"><div class="loading-state">Opening your library…</div></div>
    ${newArticleDialogMarkup(icon("close"))}
  </main>`, "library");
  setupShell(); bindLinks();

  const content = document.querySelector<HTMLElement>("#library-content")!;
  let articles: Article[] = [];
  const streams = new LibraryProgressStreams((update) => {
    articles = articles.map((candidate) => candidate.id === update.id ? { ...candidate, ...update } : candidate);
    paint();
  });
  scope.add(() => streams.close());
  const paint = (): void => {
    const query = (document.querySelector<HTMLInputElement>("#library-search")?.value ?? "").toLowerCase();
    const sort = document.querySelector<HTMLSelectElement>("#library-sort")?.value ?? "recent";
    const filtered = articles.filter((article) => `${article.title} ${article.author} ${article.sourceUrl}`.toLowerCase().includes(query));
    filtered.sort((a, b) => sort === "title" ? a.title.localeCompare(b.title) : sort === "source" ? (a.site ?? a.sourceUrl ?? "").localeCompare(b.site ?? b.sourceUrl ?? "") : (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
    if (!filtered.length) { content.innerHTML = `<div class="empty-state"><h2>${articles.length ? "No matching articles" : "Your library is ready"}</h2><p>${articles.length ? "Try another search." : "Add a URL or paste Markdown to create your first listening article."}</p></div>`; return; }
    const order: Article["status"][] = ["processing", "ready", "failed", "trashed"];
    content.innerHTML = order.map((status) => {
      const group = filtered.filter((article) => article.status === status);
      return group.length ? `<section class="library-group"><div class="group-heading"><h2>${status[0]!.toUpperCase()}${status.slice(1)}</h2><span>${group.length}</span></div><div class="card-grid">${group.map(articleCard).join("")}</div></section>` : "";
    }).join("");
    bindLinks();
  };
  try {
    articles = await api.listArticles();
    if (scope.disposed) return;
    paint();
    streams.sync(articles);
  } catch (error) { if (scope.disposed) return; content.innerHTML = `<div class="error-state"><h2>Library unavailable</h2><p>${escape(error instanceof Error ? error.message : "Could not reach Lazyread")}</p><button class="secondary-button" id="retry-library">Try again</button></div>`; document.querySelector("#retry-library")?.addEventListener("click", () => void route()); }

  document.querySelector("#library-search")?.addEventListener("input", paint);
  document.querySelector("#library-sort")?.addEventListener("change", paint);
  const dialog = document.querySelector<HTMLDialogElement>("#new-dialog")!;
  document.querySelector("#new-article")?.addEventListener("click", () => dialog.showModal());
  document.querySelector("#create-article")?.addEventListener("click", async (event) => {
    event.preventDefault();
    const url = document.querySelector<HTMLInputElement>("#new-url")!.value.trim();
    const markdown = document.querySelector<HTMLTextAreaElement>("#new-markdown")!.value.trim();
    const errorElement = document.querySelector<HTMLElement>("#form-error")!;
    if (!url && !markdown) { errorElement.textContent = "Add a URL or paste Markdown."; return; }
    try { const article = await api.create({ url: url || undefined, markdown: markdown || undefined }); dialog.close(); setRoute(article.route); }
    catch (error) { errorElement.textContent = error instanceof Error ? error.message : "Could not create article"; }
  });
  content.addEventListener("click", async (event) => {
    const button = (event.target as Element).closest<HTMLButtonElement>("[data-action]");
    if (!button) return;
    const card = button.closest<HTMLElement>("[data-id]");
    if (!card) return;
    const action = button.dataset.action as "trash" | "restore" | "retry";
    button.disabled = true;
    try { const updated = await api.action(card.dataset.id!, action); if (scope.disposed) return; articles = articles.map((article) => article.id === card.dataset.id && updated ? updated : article); paint(); streams.sync(articles); }
    catch { button.disabled = false; }
  });
}

const RATES = [0.8, 1, 1.15, 1.3, 1.5, 1.75, 2];

function prop(label: string, value?: string): string { return value && value !== "—" ? `<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>` : ""; }

async function renderReader(id: string, scope: CleanupScope): Promise<void> {
  app.innerHTML = shell(`<main class="reader-page"><div class="loading-state">Opening article…</div></main>`, "reader"); setupShell(); bindLinks();
  let article: Article;
  try { article = await api.getArticle(id); } catch (error) { if (scope.disposed) return; app.innerHTML = shell(`<main class="reader-page"><div class="error-state"><h1>Article unavailable</h1><p>${escape(error instanceof Error ? error.message : "Article not found")}</p><a href="/library" data-link class="secondary-button">Return to library</a></div></main>`, "reader"); setupShell(); bindLinks(); return; }
  if (scope.disposed) return;
  document.title = `${article.title} · Lazyread`;
  const production = article.productionSeconds ? formatTime(article.productionSeconds) : undefined;
  const progress = article.progress;
  app.innerHTML = shell(`<main class="reader-page" id="top">
    <section class="article-hero"><p class="eyebrow">${escape(article.site ?? "Listening article")}${article.publishedAt ? ` · ${date(article.publishedAt)}` : ""}</p><h1>${escape(article.title)}</h1>${article.description ? `<p class="dek">${escape(article.description)}</p>` : ""}<div class="byline">${article.author ? `<span>By ${escape(article.author)}</span>` : ""}<span>${article.wordCount?.toLocaleString() ?? "—"} words</span><span id="listen-duration">${article.durationSeconds ? `${Math.round(article.durationSeconds / 60)} min listen` : "Narration preparing"}</span></div>
      <dl class="article-props">${prop("Source", article.site ?? (article.sourceUrl ? new URL(article.sourceUrl).hostname : undefined))}${prop("Created", date(article.createdAt))}${prop("Voice", article.voice)}${prop("Model", article.model)}${prop("Provider", article.provider)}${prop("Production", production)}${prop("Peak memory", size(article.peakMemoryBytes))}${prop("Audio", size(article.artifactBytes))}</dl>
      ${article.sourceUrl ? `<a class="source-pill liquid" target="_blank" rel="noreferrer" href="${escape(article.sourceUrl)}">Original source ${icon("source")}</a>` : ""}
      <div class="article-job status-${article.status}" id="article-job" ${article.status === "ready" ? "hidden" : ""}><span class="status-dot"></span><div><strong id="job-phase">${escape(statusLabel(article))}</strong><p id="job-detail">${escape(article.error ?? (progress ? `${Math.round(progress.percent)}% complete` : "Text is ready while local narration continues."))}</p></div>${progress ? `<div class="job-progress"><i id="job-progress-bar" style="width:${progress.percent}%"></i></div>` : ""}</div>
    </section>
    ${article.warnings.length ? `<aside class="warnings" aria-label="Article warnings">${article.warnings.map((warning) => `<p>${escape(warning)}</p>`).join("")}</aside>` : ""}
    <div class="reader-layout"><aside class="rail"><div class="rail-sticky"><p class="rail-label">In this article</p><nav id="toc"></nav><div class="listen-status"><span class="status-dot" id="audio-dot"></span><span id="audio-status">${article.status === "ready" ? "Checking narration" : "Narration in progress"}</span></div></div></aside><article class="reader-prose" id="article-body">${articleMarkup(article.html, article.markdown)}</article></div>
  </main>
  <div class="reader-dock" id="reader-dock"><aside class="shortcut-hud" aria-label="Keyboard shortcuts"><span>Shortcuts</span><dl><div><dt>H</dt><dd>mark</dd></div><div><dt>⇧ H</dt><dd>prior</dd></div><div><dt>U</dt><dd>undo</dd></div><div><dt>↵</dt><dd>play / pause</dd></div><div><dt>P</dt><dd>next ¶</dd></div><div><dt>⇧ P</dt><dd>prior ¶</dd></div><div><dt>W</dt><dd>next word</dd></div><div><dt>B</dt><dd>prior word</dd></div><div><dt>S</dt><dd>faster</dd></div><div><dt>⇧ S</dt><dd>slower</dd></div></dl></aside>
    <div class="player-shell liquid"><button class="play-button" id="play-button" disabled aria-label="Play article">${icon("play")}</button><div class="player-main"><div class="player-meta"><span><b id="player-state">${article.status === "ready" ? "Preparing playback" : "Narration in progress"}</b><strong id="current-section">${escape(article.title)}</strong></span><small id="download-status">${article.status === "ready" ? "Loading timings" : "You can read now"}</small></div><div class="timeline-row"><span id="current-time">0:00</span><input id="timeline" type="range" min="0" max="1000" value="0" disabled aria-label="Article progress"/><span id="duration">—:——</span></div></div><div class="player-actions"><button class="speed-button liquid" id="speed-button" disabled aria-label="Playback speed, 1×" aria-expanded="false">${icon("speed")}<span id="speed-value">1×</span></button><button class="highlight-button liquid" id="highlight-button" aria-label="Open highlights" aria-expanded="false">${icon("highlights")}<span id="highlight-count" hidden>0</span></button></div></div>
    <div class="speed-menu liquid" id="speed-menu" hidden>${RATES.map((rate) => `<button data-rate="${rate}" aria-pressed="${rate === 1}">${rate}×</button>`).join("")}</div>
    <section class="highlight-panel liquid" id="highlight-panel" hidden><header><div><span>Reading notes</span><h2>Highlights</h2></div><button id="highlight-close" aria-label="Close highlights">${icon("close")}</button></header><p id="highlight-empty">Press H for the current sentence or ⇧ H for the previous one.</p><ol id="highlight-list"></ol><footer><button id="copy-highlights">Copy highlights</button><button class="primary-button" id="copy-ai">Copy for AI</button></footer><p id="copy-status" aria-live="polite"></p></section>
  </div><audio id="audio" preload="none"></audio>`, "reader");
  setupShell(); bindLinks();

  const articleBody = document.querySelector<HTMLElement>("#article-body")!;
  const duplicateTitle = articleBody.querySelector<HTMLElement>(":scope > h1:first-child");
  if (duplicateTitle?.textContent?.trim().toLocaleLowerCase() === article.title.trim().toLocaleLowerCase()) duplicateTitle.hidden = true;
  const headings = [...articleBody.querySelectorAll<HTMLHeadingElement>("h2, h3")];
  const toc = document.querySelector<HTMLElement>("#toc")!;
  headings.slice(0, 12).forEach((heading, index) => { heading.id ||= `section-${index + 1}`; const link = document.createElement("a"); link.href = `#${heading.id}`; link.textContent = heading.textContent; toc.append(link); });

  let stream: ProgressStream | null = null;
  if (article.status !== "ready" && article.status !== "failed" && article.status !== "trashed") {
    stream = new ProgressStream(article.id, (update) => {
      article = { ...article, ...update };
      const phase = document.querySelector("#job-phase"); const detail = document.querySelector("#job-detail"); const bar = document.querySelector<HTMLElement>("#job-progress-bar");
      if (phase) phase.textContent = statusLabel(article);
      if (detail) detail.textContent = article.progress ? `${Math.round(article.progress.percent)}% complete${article.progress.etaSeconds ? ` · ${formatTime(article.progress.etaSeconds)} remaining` : ""}` : "Text is ready while local narration continues.";
      if (bar && article.progress) bar.style.width = `${article.progress.percent}%`;
      if (article.status === "ready") { stream?.close(); window.location.reload(); }
    }); stream.open();
  }
  scope.add(() => stream?.close());
  if (article.status !== "ready") return;
  await setupPlayer(article, articleBody, scope);
}

async function setupPlayer(article: Article, articleBody: HTMLElement, scope: CleanupScope): Promise<void> {
  const required = <T extends Element>(selector: string): T => document.querySelector<T>(selector)!;
  const audio = required<HTMLAudioElement>("#audio"); const play = required<HTMLButtonElement>("#play-button"); const timeline = required<HTMLInputElement>("#timeline");
  const playerState = required<HTMLElement>("#player-state"); const download = required<HTMLElement>("#download-status"); const currentTime = required<HTMLElement>("#current-time"); const duration = required<HTMLElement>("#duration"); const audioStatus = required<HTMLElement>("#audio-status"); const audioDot = required<HTMLElement>("#audio-dot");
  let manifest: AudioManifest | undefined = article.manifest;
  try {
    if (!manifest) {
      const manifestUrl = article.timingsUrl ?? `/api/articles/${encodeURIComponent(article.id)}/timings`;
      const response = await fetch(manifestUrl, { cache: "no-cache" });
      if (!response.ok) throw new Error("Narration timings are unavailable");
      manifest = normalizeManifest(await response.json());
    }
    if (!manifest) throw new Error("Narration manifest is incomplete");
  } catch (error) { playerState.textContent = "Narration unavailable"; download.textContent = error instanceof Error ? error.message : "Could not load timings"; audioDot.classList.add("error"); return; }
  if (scope.disposed) return;
  const words = manifest.words; const wordElements = attachWordTimings(articleBody, words); const timed = new Set(words.map((word) => word.index)); const wordIndexes = [...timed].sort((a, b) => a - b); const paragraphs = [...new Set([...articleBody.querySelectorAll<HTMLElement>("p, li, blockquote, h2, h3")].flatMap((block) => { const first = [...block.querySelectorAll<HTMLElement>("[data-word-index]")].map((element) => Number(element.dataset.wordIndex)).find((index) => timed.has(index)); return first === undefined ? [] : [first]; }))].sort((a, b) => a - b);
  const ranges = sentenceRanges(words); let activeIndex = words[0]?.index ?? 0; let activeElement: HTMLElement | null = null; let frame = 0; let blobUrl = ""; const undo: Array<() => void> = [];
  const readingTracker = createReadingTracker();
  const localHighlights = JSON.parse(migratedStorageValue(localStorage, `lazyread-highlights:${article.id}`, `lazyreader-highlights:${article.id}`, `listen-read-highlights:${article.id}`) ?? "[]") as Highlight[];
  let highlights: Highlight[] = article.highlights?.length ? article.highlights : localHighlights;
  const saveHighlights = (): void => { localStorage.setItem(`lazyread-highlights:${article.id}`, JSON.stringify(highlights)); paintHighlights(); void api.saveHighlights(article.id, highlights).catch(() => { required("#copy-status").textContent = "Highlights remain on this browser; library sync will retry after the server reconnects."; }); };
  const paintHighlights = (): void => {
    articleBody.querySelectorAll(".is-saved").forEach((element) => element.classList.remove("is-saved"));
    highlights.forEach((highlight) => { for (let index = highlight.startIndex; index <= highlight.endIndex; index += 1) wordElements.get(index)?.classList.add("is-saved"); });
    const list = required<HTMLOListElement>("#highlight-list"); list.innerHTML = highlights.map((highlight) => `<li><span>${escape(highlight.text)}</span><button data-remove="${escape(highlight.id)}" aria-label="Remove highlight">${icon("close")}</button></li>`).join("");
    required<HTMLElement>("#highlight-empty").hidden = highlights.length > 0; const count = required<HTMLElement>("#highlight-count"); count.textContent = String(highlights.length); count.hidden = !highlights.length;
  };
  paintHighlights();
  required("#highlight-list").addEventListener("click", (event) => { const button = (event.target as Element).closest<HTMLButtonElement>("[data-remove]"); if (!button) return; const removed = highlights.find((item) => item.id === button.dataset.remove); highlights = highlights.filter((item) => item.id !== button.dataset.remove); if (removed) undo.push(() => { highlights = [...highlights, removed]; saveHighlights(); }); saveHighlights(); });
  const panel = required<HTMLElement>("#highlight-panel"); const highlightButton = required<HTMLButtonElement>("#highlight-button");
  const togglePanel = (open = panel.hidden): void => { panel.hidden = !open; highlightButton.ariaExpanded = String(open); };
  highlightButton.addEventListener("click", () => togglePanel()); required("#highlight-close").addEventListener("click", () => togglePanel(false));
  const copy = async (ai: boolean): Promise<void> => { const selected = highlights.map((item) => `- ${item.text}`).join("\n"); const text = ai ? `# Highlights from ${article.title}\n\nSource: ${article.sourceUrl ?? "Local article"}\n\n## Selected passages\n\n${selected}\n\n## Flattened article\n\n${plainArticleText(articleBody)}` : selected; await navigator.clipboard.writeText(text); required("#copy-status").textContent = ai ? "Article and highlights copied for AI." : "Highlights copied."; };
  required("#copy-highlights").addEventListener("click", () => void copy(false)); required("#copy-ai").addEventListener("click", () => void copy(true));
  duration.textContent = formatTime(manifest.duration); required("#listen-duration").textContent = `${Math.round(manifest.duration / 60)} min listen`;
  const audioUrl = article.audioUrl ?? manifest.audio; const revision = article.audioRevision ?? manifest.revision ?? `${article.id}-${article.updatedAt ?? "ready"}`;
  try {
    const blob = await preloadCompleteAudio(audioUrl, revision, ({ loaded, total, percent }) => { playerState.textContent = "Downloading for uninterrupted playback"; download.textContent = total ? `${Math.round(percent)}% · ${size(loaded)} of ${size(total)}` : `${size(loaded)} downloaded`; audioStatus.textContent = `Caching narration · ${Math.round(percent)}%`; });
    blobUrl = URL.createObjectURL(blob);
    scope.add(() => { if (blobUrl) URL.revokeObjectURL(blobUrl); });
    if (scope.disposed) return;
    audio.src = blobUrl; await new Promise<void>((resolve, reject) => { audio.addEventListener("canplaythrough", () => resolve(), { once: true }); audio.addEventListener("error", () => reject(new Error("Browser could not decode narration")), { once: true }); audio.load(); });
    if (scope.disposed) return;
    play.disabled = false; timeline.disabled = false; required<HTMLButtonElement>("#speed-button").disabled = false; playerState.textContent = "Ready to listen"; download.textContent = `${size(blob.size)} · available offline`; audioStatus.textContent = "Narration ready offline"; audioDot.classList.add("ready");
  } catch (error) { playerState.textContent = "Narration unavailable"; download.textContent = error instanceof Error ? error.message : "Download failed"; audioDot.classList.add("error"); return; }
  // Track the last started word when the playhead sits in a silence gap (figure
  // pauses, section breaks) so keyboard navigation stays anchored where the
  // listener actually is.
  // The tracking clock adds a small epsilon: seeking to a word boundary snaps
  // currentTime a hair below the requested start, which would otherwise resolve
  // to the previous word and clobber the seek.
  const timingByIndex = new Map<number, (typeof words)[number]>(); for (const word of words) if (!timingByIndex.has(word.index)) timingByIndex.set(word.index, word);
  const update = (): void => { cancelAnimationFrame(frame); const clock = audio.currentTime + 0.002; const contained = findWordAtTime(words, clock); const position = contained >= 0 ? contained : lastWordStartedBefore(words, clock); if (position >= 0) { const timing = words[position]!; if (timingByIndex.get(activeIndex)?.start !== timing.start) activeIndex = timing.index; const next = wordElements.get(activeIndex); if (next && next !== activeElement) { activeElement?.classList.remove("is-current"); activeElement = next; next.classList.add("is-current"); const heading = [...articleBody.querySelectorAll("h2, h3")].filter((item) => item.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).at(-1); required("#current-section").textContent = heading?.textContent ?? article.title; } } readingTracker.track(activeElement, audio.paused); currentTime.textContent = formatTime(audio.currentTime); timeline.value = String(audio.duration ? Math.round(audio.currentTime / audio.duration * 1000) : 0); timeline.style.setProperty("--progress", `${Number(timeline.value) / 10}%`); if (!audio.paused) frame = requestAnimationFrame(update); };
  const seek = (index: number): void => { const timing = words.find((word) => word.index === index) ?? words.find((word) => word.index > index) ?? [...words].reverse().find((word) => word.index < index); const element = timing && wordElements.get(timing.index); if (!timing || !element) return; const previous = audio.currentTime; undo.push(() => { audio.currentTime = previous; update(); }); audio.currentTime = timing.start; activeIndex = timing.index; readingTracker.resume(); update(); readingTracker.reveal(element); };
  const toggle = async (): Promise<void> => { if (play.disabled) return; if (audio.paused) await audio.play(); else audio.pause(); };
  play.addEventListener("click", () => void toggle()); audio.addEventListener("play", () => { readingTracker.start(); play.innerHTML = icon("pause"); play.ariaLabel = "Pause article"; cancelAnimationFrame(frame); frame = requestAnimationFrame(update); }); audio.addEventListener("pause", () => { readingTracker.stop(); play.innerHTML = icon("play"); play.ariaLabel = "Play article"; cancelAnimationFrame(frame); update(); }); audio.addEventListener("ended", () => { readingTracker.stop(); play.innerHTML = icon("retry"); play.ariaLabel = "Replay article"; });
  timeline.addEventListener("input", () => { audio.currentTime = Number(timeline.value) / 1000 * audio.duration; readingTracker.resume(); update(); });
  audio.addEventListener("timeupdate", update);
  articleBody.addEventListener("click", (event) => { const word = (event.target as Element).closest<HTMLElement>("[data-word-index]"); if (word) seek(Number(word.dataset.wordIndex)); });
  const noteManualInteraction = (): void => readingTracker.noteManualInteraction();
  scope.listen(window, "wheel", noteManualInteraction, { passive: true });
  scope.listen(window, "touchstart", noteManualInteraction, { passive: true });
  const speedButton = required<HTMLButtonElement>("#speed-button"); const speedMenu = required<HTMLElement>("#speed-menu"); speedButton.addEventListener("click", () => { speedMenu.hidden = !speedMenu.hidden; speedButton.ariaExpanded = String(!speedMenu.hidden); });
  const setRate = (rate: number): void => { audio.playbackRate = rate; required("#speed-value").textContent = `${rate}×`; speedButton.ariaLabel = `Playback speed, ${rate}×`; speedMenu.querySelectorAll("button").forEach((item) => item.ariaPressed = String(Number(item.dataset.rate) === rate)); };
  const stepRate = (direction: "up" | "down"): void => { const current = RATES.reduce((nearest, rate, position) => Math.abs(rate - audio.playbackRate) < Math.abs(RATES[nearest]! - audio.playbackRate) ? position : nearest, 0); const next = RATES[Math.min(RATES.length - 1, Math.max(0, current + (direction === "up" ? 1 : -1)))]!; setRate(next); };
  speedMenu.addEventListener("click", (event) => { const button = (event.target as Element).closest<HTMLButtonElement>("[data-rate]"); if (!button) return; setRate(Number(button.dataset.rate)); speedMenu.hidden = true; speedButton.ariaExpanded = "false"; });
  const onKeyDown = (event: KeyboardEvent): void => { const shortcut = getShortcut(event); if (!shortcut || !shouldHandleShortcut(event, shortcut)) return; event.preventDefault(); if (shortcut.type === "toggle") void toggle(); else if (shortcut.type === "undo") undo.pop()?.(); else if (shortcut.type === "speed") stepRate(shortcut.direction); else if (shortcut.type === "word" || shortcut.type === "paragraph") { const next = adjacentIndex(shortcut.type === "word" ? wordIndexes : paragraphs, activeIndex, shortcut.direction); if (next !== null) seek(next); } else { const range = sentenceAt(ranges, activeIndex, shortcut.previous); if (range) { const before = highlights; undo.push(() => { highlights = before; saveHighlights(); }); highlights = toggleHighlight(highlights, range); saveHighlights(); } } };
  scope.listen(document, "keydown", onKeyDown as EventListener);
  scope.add(() => { readingTracker.stop(); cancelAnimationFrame(frame); });
}

async function route(): Promise<void> {
  routeScope.dispose();
  routeScope = new CleanupScope();
  const scope = routeScope;
  const match = location.pathname.match(/^\/read\/([^/]+)/);
  if (match) await renderReader(decodeURIComponent(match[1]!), scope);
  else await renderLibrary(scope);
}

const storedTheme = migratedStorageValue(localStorage, "lazyread-theme", "lazyreader-theme", "listen-read-theme");
if (storedTheme === "dark" || (!storedTheme && matchMedia("(prefers-color-scheme: dark)").matches)) document.documentElement.classList.add("dark");
initLiquidGlass();
window.addEventListener("popstate", () => void route());
void route();
