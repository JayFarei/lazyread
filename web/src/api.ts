import type { Article, ArticleStatus, AudioManifest, Highlight, Progress, WordTiming } from "./types";

type JsonObject = Record<string, unknown>;
type FetchLike = typeof fetch;

const object = (value: unknown): JsonObject =>
  value && typeof value === "object" ? value as JsonObject : {};
const string = (value: unknown): string | undefined =>
  typeof value === "string" && value.length > 0 ? value : undefined;
const number = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

function statusOf(raw: JsonObject): ArticleStatus {
  const value = string(raw.status) ?? string(raw.state) ?? "processing";
  if (value === "ready" || value === "failed" || value === "trashed") return value;
  return "processing";
}

function normalizeWords(value: unknown): WordTiming[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item, position) => {
    const raw = object(item);
    const text = string(raw.text);
    const start = number(raw.start);
    const end = number(raw.end);
    if (!text || start === undefined || end === undefined) return [];
    const hasDisplayIdentity = Object.prototype.hasOwnProperty.call(raw, "display_word_id") || Object.prototype.hasOwnProperty.call(raw, "displayWordId");
    return [{
      index: number(raw.index) ?? position,
      text,
      start,
      end,
      displayWordId: hasDisplayIdentity ? (string(raw.display_word_id) ?? string(raw.displayWordId) ?? null) : undefined,
      sentenceEnd: raw.sentence_end === true || raw.sentenceEnd === true,
      sentenceSuffix: string(raw.sentence_suffix) ?? string(raw.sentenceSuffix),
    }];
  });
}

export function normalizeManifest(value: unknown): AudioManifest | undefined {
  const raw = object(value);
  const audio = string(raw.audio) ?? string(raw.url);
  const duration = number(raw.duration) ?? number(raw.duration_seconds);
  const words = normalizeWords(raw.words ?? raw.timings);
  if (!audio || duration === undefined || words.length === 0) return undefined;
  return {
    audio,
    duration,
    words,
    bytes: number(raw.bytes) ?? number(raw.size_bytes),
    revision: string(raw.revision) ?? string(raw.audio_revision),
    voice: string(raw.voice),
    model: string(raw.model),
    modelRevision: string(raw.modelRevision) ?? string(raw.model_revision),
    aligner: string(raw.aligner),
    alignerRevision: string(raw.alignerRevision) ?? string(raw.aligner_revision),
  };
}

export function normalizeArticle(value: unknown): Article {
  const raw = object(value);
  const metadata = object(raw.metadata);
  const job = object(raw.job);
  const audio = object(raw.audio);
  const telemetry = object(raw.telemetry);
  const progressRaw = object(raw.progress ?? job.progress);
  const completed = number(progressRaw.completed) ?? number(job.completed) ?? 0;
  const total = number(progressRaw.total) ?? number(job.total) ?? 0;
  const explicitPercent = number(progressRaw.percent);
  const progress: Progress | undefined = total > 0 || explicitPercent !== undefined ? {
    completed,
    total,
    percent: explicitPercent ?? (total ? completed / total * 100 : 0),
    etaSeconds: number(progressRaw.eta_seconds) ?? number(progressRaw.etaSeconds) ?? number(job.eta_seconds),
  } : undefined;
  const id = string(raw.id) ?? "unknown";
  const warnings = raw.warnings;
  const rawHighlights = raw.highlights;

  return {
    id,
    status: statusOf(raw),
    state: string(raw.state),
    title: string(raw.title) ?? string(metadata.title) ?? "Untitled article",
    description: string(raw.description) ?? string(metadata.description),
    author: string(raw.author) ?? string(metadata.author),
    site: string(raw.site) ?? string(metadata.site),
    sourceUrl: string(raw.source_url) ?? string(raw.sourceUrl) ?? string(metadata.source),
    publishedAt: string(raw.published_at) ?? string(raw.publishedAt) ?? string(metadata.published),
    createdAt: string(raw.created_at) ?? string(raw.createdAt),
    updatedAt: string(raw.updated_at) ?? string(raw.updatedAt),
    wordCount: number(raw.word_count) ?? number(raw.wordCount) ?? number(metadata.wordCount),
    durationSeconds: number(raw.duration_seconds) ?? number(raw.durationSeconds) ?? number(audio.duration),
    route: string(raw.route) ?? `/read/${encodeURIComponent(id)}`,
    phase: string(raw.phase) ?? string(job.phase),
    progress,
    error: string(raw.error) ?? string(job.error),
    markdown: string(raw.markdown) ?? string(object(raw.content).markdown),
    html: string(raw.content_html) ?? string(raw.html) ?? string(object(raw.content).html),
    audioUrl: string(raw.audio_url) ?? string(audio.url) ?? string(audio.audio),
    timingsUrl: string(raw.timings_url) ?? string(audio.timings_url),
    audioRevision: string(raw.audio_revision) ?? string(audio.revision),
    manifest: normalizeManifest(raw.manifest ?? (Array.isArray(audio.words) ? audio : undefined)),
    voice: string(raw.voice) ?? string(audio.voice),
    model: string(raw.model) ?? string(audio.model),
    provider: string(raw.provider) ?? string(audio.provider),
    productionSeconds: number(raw.production_seconds) ?? number(telemetry.wall_seconds),
    peakMemoryBytes: number(raw.peak_memory_bytes) ?? number(telemetry.peak_rss_bytes),
    artifactBytes: number(raw.artifact_bytes) ?? number(audio.bytes),
    warnings: Array.isArray(warnings) ? warnings.filter((item): item is string => typeof item === "string") : [],
    highlights: Array.isArray(rawHighlights) ? rawHighlights.flatMap((item) => {
      const highlight = object(item); const id = string(highlight.id); const text = string(highlight.text); const startIndex = number(highlight.startIndex); const endIndex = number(highlight.endIndex);
      return id && text && startIndex !== undefined && endIndex !== undefined ? [{ id, text, startIndex, endIndex }] : [];
    }) : undefined,
  };
}

function normalizeEnvelope(value: unknown): Article {
  const payload = object(value);
  return normalizeArticle(payload.article ? { ...object(payload.article), job: payload.job } : payload);
}

export class ApiClient {
  constructor(
    private readonly base = "",
    private readonly fetcher: FetchLike = (...arguments_) => fetch(...arguments_),
  ) {}

  private async json(path: string, init?: RequestInit): Promise<JsonObject> {
    const response = await this.fetcher(`${this.base}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
    const payload = object(await response.json().catch(() => ({})));
    if (!response.ok) throw new Error(string(payload.error) ?? string(payload.detail) ?? `Request failed (${response.status})`);
    return payload;
  }

  async listArticles(): Promise<Article[]> {
    const payload = await this.json("/api/articles?include_trashed=1");
    const items = Array.isArray(payload.articles) ? payload.articles : [];
    return items.map(normalizeArticle);
  }

  async getArticle(id: string): Promise<Article> {
    const payload = await this.json(`/api/articles/${encodeURIComponent(id)}`);
    return normalizeEnvelope(payload);
  }

  async create(input: { url?: string; markdown?: string }): Promise<Article> {
    const payload = await this.json("/api/articles", { method: "POST", body: JSON.stringify({ ...input, source_url: input.url }) });
    return normalizeArticle(payload.article ?? payload);
  }

  async action(id: string, action: "trash" | "restore" | "purge" | "retry"): Promise<Article | null> {
    const path = action === "purge" ? `/api/articles/${encodeURIComponent(id)}` : `/api/articles/${encodeURIComponent(id)}/${action}`;
    const payload = await this.json(path, { method: action === "purge" ? "DELETE" : "POST" });
    return payload.article ? normalizeEnvelope(payload) : null;
  }

  async saveHighlights(id: string, highlights: Highlight[]): Promise<void> {
    await this.json(`/api/articles/${encodeURIComponent(id)}/highlights`, {
      method: "PUT",
      body: JSON.stringify({ highlights }),
    });
  }
}

type EventSourceLike = {
  addEventListener(type: string, listener: EventListener): void;
  onerror: ((event: Event) => void) | null;
  close(): void;
};
type EventSourceConstructor = new (url: string) => EventSourceLike;

export class ProgressStream {
  private source: EventSourceLike | null = null;
  private current: Article | null = null;
  cursor = "";

  constructor(
    private readonly id: string,
    private readonly onUpdate: (article: Article) => void,
    private readonly Source: EventSourceConstructor = EventSource,
  ) {}

  open(): void {
    this.close();
    const cursor = this.cursor ? `?since=${encodeURIComponent(this.cursor)}` : "";
    this.source = new this.Source(`/api/articles/${encodeURIComponent(this.id)}/events${cursor}`);
    const receive = ((event: MessageEvent) => {
      this.cursor = event.lastEventId || this.cursor;
      try {
        const payload = object(JSON.parse(event.data as string));
        const update = payload.article
          ? normalizeEnvelope(payload)
          : normalizeArticle({
              id: this.id,
              title: this.current?.title ?? "Untitled article",
              status: payload.status ?? payload.state ?? this.current?.status ?? "processing",
              ...payload,
              job: event.type === "job" ? payload : payload.job,
            });
        this.current = this.current ? { ...this.current, ...update } : update;
        this.onUpdate(this.current);
      } catch { /* Ignore an incomplete server event and wait for its next snapshot. */ }
    }) as EventListener;
    for (const name of ["snapshot", "progress", "job", "article", "message"]) this.source.addEventListener(name, receive);
  }

  close(): void {
    this.source?.close();
    this.source = null;
  }
}
