import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const sourceUrl = process.argv[2];
if (!sourceUrl || !/^https?:\/\//.test(sourceUrl)) {
  throw new Error("Usage: node scripts/fetch-article.mjs <https-url> [output.md]");
}
const defuddleUrl = `https://defuddle.md/${sourceUrl}`;
const outputPath = path.resolve(process.argv[3] ?? "content/article.md");

const response = await fetch(defuddleUrl);
if (!response.ok) {
  throw new Error(`Defuddle returned ${response.status} ${response.statusText}`);
}

const markdown = await response.text();

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, markdown.trimEnd() + "\n", "utf8");
console.log(`Saved clean article Markdown to ${outputPath}`);
