import { ProgressStream } from "./api";
import type { Article } from "./types";

type Stream = Pick<ProgressStream, "open" | "close">;
type StreamFactory = (id: string, onUpdate: (article: Article) => void) => Stream;

export class LibraryProgressStreams {
  private readonly streams = new Map<string, Stream>();

  constructor(
    private readonly onUpdate: (article: Article) => void,
    private readonly create: StreamFactory = (id, update) => new ProgressStream(id, update),
  ) {}

  sync(articles: Article[]): void {
    const processing = new Set(articles.filter((article) => article.status === "processing").map((article) => article.id));
    for (const id of this.streams.keys()) if (!processing.has(id)) this.stop(id);
    for (const id of processing) {
      if (this.streams.has(id)) continue;
      const stream = this.create(id, (update) => {
        this.onUpdate(update);
        if (update.status !== "processing") this.stop(id);
      });
      this.streams.set(id, stream);
      stream.open();
    }
  }

  close(): void {
    for (const id of [...this.streams.keys()]) this.stop(id);
  }

  private stop(id: string): void {
    const stream = this.streams.get(id);
    if (!stream) return;
    this.streams.delete(id);
    stream.close();
  }
}

export function newArticleDialogMarkup(closeIcon: string): string {
  return `<dialog id="new-dialog" aria-labelledby="new-dialog-title"><form method="dialog" class="new-form"><div class="dialog-heading"><div><span class="eyebrow">Add to library</span><h2 id="new-dialog-title">New listening article</h2></div><button value="cancel" class="icon-button" aria-label="Close">${closeIcon}</button></div><label>URL<input id="new-url" type="url" placeholder="https://…" /></label><div class="or"><span>or paste Markdown</span></div><label>Markdown<textarea id="new-markdown" rows="9" placeholder="# Article title\n\nArticle text…"></textarea></label><p class="form-error" id="form-error" role="alert"></p><button class="primary-button" id="create-article" value="create">Create article</button></form></dialog>`;
}
