export type WordTiming = {
  index: number;
  text: string;
  start: number;
  end: number;
};

export function findWordAtTime(words: WordTiming[], time: number): number {
  if (words.length === 0 || time < words[0]!.start) return -1;

  let low = 0;
  let high = words.length - 1;
  let answer = -1;

  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const word = words[middle]!;
    if (word.start <= time) {
      answer = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }

  if (answer === -1) return -1;
  return time <= words[answer]!.end + 0.18 ? answer : -1;
}

export function formatTime(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "0:00";
  const seconds = Math.floor(totalSeconds % 60);
  const minutes = Math.floor(totalSeconds / 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
