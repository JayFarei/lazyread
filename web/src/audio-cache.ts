export type DownloadProgress = { loaded: number; total: number; percent: number };
type AudioCache = Pick<Cache, "match" | "put">;
type AudioEnvironment = {
  cacheStorage?: { open(name: string): Promise<AudioCache> };
  fetcher?: typeof fetch;
};

// Keep the pre-release cache namespace so the product rename never redownloads
// complete narration files that may be several gigabytes in aggregate.
const AUDIO_CACHE_NAME = "listen-read-audio-v1";

export function revisionedCacheKey(url: string, revision = "current"): string {
  const join = url.includes("?") ? "&" : "?";
  return `${url}${join}listen-read-revision=${encodeURIComponent(revision)}`;
}

export async function preloadCompleteAudio(
  url: string,
  revision: string,
  onProgress: (progress: DownloadProgress) => void,
  environment: AudioEnvironment = {},
): Promise<Blob> {
  const cacheStorage = environment.cacheStorage ?? ("caches" in globalThis ? caches : undefined);
  const fetcher = environment.fetcher ?? fetch;
  if (!cacheStorage) {
    const response = await fetcher(url);
    if (!response.ok) throw new Error("Narration audio is unavailable");
    const blob = await response.blob();
    onProgress({ loaded: blob.size, total: blob.size, percent: 100 });
    return blob;
  }
  const cache = await cacheStorage.open(AUDIO_CACHE_NAME);
  const key = revisionedCacheKey(url, revision);
  const cached = await cache.match(key);
  if (cached) {
    const blob = await cached.blob();
    onProgress({ loaded: blob.size, total: blob.size, percent: 100 });
    return blob;
  }
  const response = await fetcher(url);
  if (!response.ok) throw new Error("Narration audio is unavailable");
  const total = Number(response.headers.get("content-length") ?? 0);
  if (!response.body) {
    const blob = await response.blob();
    await cache.put(key, new Response(blob, { headers: { "content-type": blob.type, "content-length": String(blob.size) } }));
    onProgress({ loaded: blob.size, total: blob.size, percent: 100 });
    return blob;
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) { chunks.push(value); loaded += value.byteLength; }
    onProgress({ loaded, total, percent: total ? Math.min(100, loaded / total * 100) : 0 });
  }
  const blob = new Blob(chunks as BlobPart[], { type: response.headers.get("content-type") ?? "audio/flac" });
  await cache.put(key, new Response(blob, { headers: { "content-type": blob.type, "content-length": String(blob.size) } }));
  onProgress({ loaded: blob.size, total: total || blob.size, percent: 100 });
  return blob;
}
