// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { ApiClient, ProgressStream } from "./api";

describe("ApiClient", () => {
  it("normalizes list and single-article envelopes", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ articles: [{ id: "a", status: "ready", title: "A" }] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ article: { id: "a", state: "text_ready", title: "A" } })));
    const api = new ApiClient("", fetcher);
    expect((await api.listArticles())[0]?.status).toBe("ready");
    expect((await api.getArticle("a")).status).toBe("processing");
  });

  it("throws the server detail for failed requests", async () => {
    const api = new ApiClient("", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "No article" }), { status: 404 })));
    await expect(api.getArticle("gone")).rejects.toThrow("No article");
  });
});

describe("ProgressStream", () => {
  it("maps snapshot payloads into article updates and reconnects from last event id", () => {
    const sources: FakeEventSource[] = [];
    class FakeEventSource {
      listeners = new Map<string, EventListener>();
      url: string;
      onerror: (() => void) | null = null;
      constructor(url: string) { this.url = url; sources.push(this); }
      addEventListener(name: string, callback: EventListener) { this.listeners.set(name, callback); }
      close() {}
    }
    const updates: string[] = [];
    const stream = new ProgressStream("a", (article) => updates.push(article.phase ?? ""), FakeEventSource as never);
    stream.open();
    sources[0]?.listeners.get("snapshot")?.({ data: JSON.stringify({ article: { id: "a", status: "processing", phase: "narrating" } }), lastEventId: "9" } as MessageEvent);
    sources[0]?.listeners.get("job")?.({ type: "job", data: JSON.stringify({ state: "aligning", phase: "aligning", completed: 3, total: 4 }), lastEventId: "10" } as MessageEvent);
    expect(updates).toEqual(["narrating", "aligning"]);
    expect(stream.cursor).toBe("10");
    stream.close();
  });
});
