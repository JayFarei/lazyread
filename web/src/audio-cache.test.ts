import { describe, expect, it } from "vitest";
import { revisionedCacheKey } from "./audio-cache";

describe("revisionedCacheKey", () => {
  it("separates changed audio artifacts", () => {
    expect(revisionedCacheKey("/a.flac", "r1")).toBe("/a.flac?listen-read-revision=r1");
    expect(revisionedCacheKey("/a.flac?download=1", "r 2")).toBe("/a.flac?download=1&listen-read-revision=r%202");
  });
});
