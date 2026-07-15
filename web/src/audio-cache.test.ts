import { describe, expect, it, vi } from "vitest";
import { preloadCompleteAudio, revisionedCacheKey } from "./audio-cache";

describe("revisionedCacheKey", () => {
  it("separates changed audio artifacts", () => {
    expect(revisionedCacheKey("/a.flac", "r1")).toBe("/a.flac?listen-read-revision=r1");
    expect(revisionedCacheKey("/a.flac?download=1", "r 2")).toBe("/a.flac?download=1&listen-read-revision=r%202");
  });

  it("reuses audio from the pre-rename cache without redownloading", async () => {
    const cachedBlob = new Blob(["audio"], { type: "audio/flac" });
    const cachedResponse = {
      blob: vi.fn(async () => cachedBlob),
    } as unknown as Response;
    const cache = {
      match: vi.fn(async () => cachedResponse),
      put: vi.fn(async () => undefined),
    };
    const open = vi.fn(async () => cache);
    const fetchAudio = vi.fn(async () => { throw new Error("should not redownload"); });

    const blob = await preloadCompleteAudio("/a.flac", "r1", () => undefined, {
      cacheStorage: { open },
      fetcher: fetchAudio,
    });

    expect(blob.size).toBe(5);
    expect(fetchAudio).not.toHaveBeenCalled();
    expect(open).toHaveBeenCalledWith("listen-read-audio-v1");
    expect(cache.put).not.toHaveBeenCalled();
  });
});
