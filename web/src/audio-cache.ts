export type DownloadProgress = { loaded: number; total: number; percent: number };

export function revisionedCacheKey(url: string, revision = "current"): string {
  const join = url.includes("?") ? "&" : "?";
  return `${url}${join}listen-read-revision=${encodeURIComponent(revision)}`;
}

export async function preloadCompleteAudio(
  url: string,
  revision: string,
  onProgress: (progress: DownloadProgress) => void,
): Promise<Blob> {
  if (!("caches" in globalThis)) {
    const response = await fetch(url);
    if (!response.ok) throw new Error("Narration audio is unavailable");
    const blob = await response.blob();
    onProgress({ loaded: blob.size, total: blob.size, percent: 100 });
    return blob;
  }
  const cache = await caches.open("listen-read-audio-v1");
  const key = revisionedCacheKey(url, revision);
  const cached = await cache.match(key);
  if (cached) {
    const blob = await cached.blob();
    onProgress({ loaded: blob.size, total: blob.size, percent: 100 });
    return blob;
  }
  const response = await fetch(url);
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
