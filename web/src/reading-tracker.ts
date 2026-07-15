export type ReadingTrackerOptions = {
  manualPauseMs?: number;
  targetViewportRatio?: number;
};

export type ReadingTracker = {
  noteManualInteraction: () => void;
  reveal: (word: HTMLElement) => void;
  resume: () => void;
  start: () => void;
  stop: () => void;
  track: (activeWord: HTMLElement | null, paused: boolean) => void;
};

export function createReadingTracker(options: ReadingTrackerOptions = {}): ReadingTracker {
  const manualPauseMs = options.manualPauseMs ?? 2_600;
  const targetViewportRatio = options.targetViewportRatio ?? 0.25;
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)") ?? { matches: false };
  let velocity = 0;
  let manualScrollUntil = 0;

  const targetTop = (): number => {
    const dockTop = document.querySelector<HTMLElement>("#reader-dock")?.getBoundingClientRect().top;
    const usableHeight = dockTop && dockTop > 0 ? dockTop : window.innerHeight;
    return Math.max(84, usableHeight * targetViewportRatio);
  };

  return {
    noteManualInteraction() {
      manualScrollUntil = performance.now() + manualPauseMs;
      velocity = 0;
    },
    reveal(word) {
      const scroller = document.scrollingElement;
      if (!scroller) return;
      const top = scroller.scrollTop + word.getBoundingClientRect().top - targetTop();
      scroller.scrollTo({ top, behavior: reducedMotion.matches ? "auto" : "smooth" });
    },
    resume() {
      manualScrollUntil = 0;
      velocity = 0;
    },
    start() {
      document.documentElement.classList.add("is-reader-tracking");
    },
    stop() {
      document.documentElement.classList.remove("is-reader-tracking");
      velocity = 0;
    },
    track(activeWord, paused) {
      if (!activeWord || paused || performance.now() < manualScrollUntil) return;

      const distance = activeWord.getBoundingClientRect().top - targetTop();
      if (reducedMotion.matches) {
        if (Math.abs(distance) > 2) window.scrollBy({ top: distance, behavior: "auto" });
        return;
      }

      velocity = (velocity + distance * 0.055) * 0.82;
      const maxStep = Math.max(16, window.innerHeight * 0.035);
      velocity = Math.max(-maxStep, Math.min(maxStep, velocity));
      if (Math.abs(distance) < 0.35 && Math.abs(velocity) < 0.1) {
        velocity = 0;
        return;
      }
      window.scrollBy({ top: velocity, behavior: "auto" });
    },
  };
}
