import type { WordTiming } from "./player";

export type AudioManifest = {
  audio: string;
  duration: number;
  voice: string;
  model: string;
  modelRevision: string;
  aligner: string;
  alignerRevision: string;
  mlxAudioRevision: string;
  wordCount: number;
  words: WordTiming[];
};

export async function preloadAudio(
  audio: HTMLAudioElement,
  source: string,
  onProgress: (percent: number) => void,
): Promise<void> {
  const cache = await caches.open("listening-reader-audio-v1");
  let audioResponse = await cache.match(source);

  if (!audioResponse) {
    const networkResponse = await fetch(source);
    if (!networkResponse.ok) throw new Error("Narration audio is unavailable");
    const total = Number(networkResponse.headers.get("content-length") ?? 0);

    if (networkResponse.body && total > 0) {
      const reader = networkResponse.body.getReader();
      const chunks: Uint8Array[] = [];
      let loaded = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) {
          chunks.push(value);
          loaded += value.byteLength;
          onProgress(Math.min(100, (loaded / total) * 100));
        }
      }
      const blob = new Blob(chunks as BlobPart[], { type: "audio/flac" });
      audioResponse = new Response(blob, {
        headers: { "content-type": "audio/flac", "content-length": String(blob.size) },
      });
      await cache.put(source, audioResponse.clone());
    } else {
      audioResponse = networkResponse;
      await cache.put(source, networkResponse.clone());
    }
  }

  const blob = await audioResponse.blob();
  audio.src = URL.createObjectURL(blob);
  await new Promise<void>((resolve, reject) => {
    audio.addEventListener("canplaythrough", () => resolve(), { once: true });
    audio.addEventListener("error", () => reject(new Error("Browser could not decode the audio")), {
      once: true,
    });
    audio.load();
  });
}
