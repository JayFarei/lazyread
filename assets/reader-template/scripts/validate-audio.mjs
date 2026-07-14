import { access, readFile } from "node:fs/promises";
import path from "node:path";

const article = JSON.parse(await readFile("src/generated/article.json", "utf8"));
const manifest = JSON.parse(await readFile("public/audio/timings.json", "utf8"));
const audioPath = path.join("public", manifest.audio.split("?")[0]);

await access(audioPath);

if (manifest.words.length !== article.words.length) {
  throw new Error(
    `Timing count ${manifest.words.length} does not match article count ${article.words.length}`,
  );
}

for (const [position, timing] of manifest.words.entries()) {
  const articleWord = article.words[position];
  if (timing.index !== articleWord.index || timing.text !== articleWord.text) {
    throw new Error(`Word identity mismatch at position ${position}`);
  }
  if (timing.start < 0 || timing.end <= timing.start || timing.end > manifest.duration + 0.01) {
    throw new Error(`Invalid timing bounds at position ${position}`);
  }
  if (position > 0 && timing.start < manifest.words[position - 1].start) {
    throw new Error(`Non-monotonic timing at position ${position}`);
  }
}

if (!manifest.audioRevision || !manifest.audio.includes(`?v=${manifest.audioRevision}`)) {
  throw new Error("Audio manifest does not contain a cache-busting revision");
}

for (const field of ["modelRevision", "alignerRevision", "mlxAudioRevision"]) {
  if (!/^[0-9a-f]{40}$/.test(manifest[field] ?? "")) {
    throw new Error(`Audio manifest does not contain a pinned ${field}`);
  }
}

console.log(
  `Validated ${manifest.words.length} synchronized words across ${(manifest.duration / 60).toFixed(1)} minutes`,
);
