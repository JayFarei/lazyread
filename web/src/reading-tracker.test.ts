// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { createReadingTracker } from "./reading-tracker";

describe("reading tracker", () => {
  it("suspends automatic following after a manual scroll and resumes explicitly", () => {
    const word = document.createElement("span");
    word.getBoundingClientRect = vi.fn(() => ({ top: 600 } as DOMRect));
    const scrollBy = vi.spyOn(window, "scrollBy").mockImplementation(() => undefined);
    const now = vi.spyOn(performance, "now").mockReturnValue(100);
    const tracker = createReadingTracker({ manualPauseMs: 2_600 });

    tracker.noteManualInteraction();
    now.mockReturnValue(200);
    tracker.track(word, false);
    expect(scrollBy).not.toHaveBeenCalled();

    tracker.resume();
    tracker.track(word, false);
    expect(scrollBy).toHaveBeenCalledOnce();
  });

  it("does not enqueue smooth scrolling for continuous playback", () => {
    const word = document.createElement("span");
    word.getBoundingClientRect = vi.fn(() => ({ top: 700 } as DOMRect));
    const scrollBy = vi.spyOn(window, "scrollBy").mockImplementation(() => undefined);
    const tracker = createReadingTracker();

    tracker.track(word, false);

    expect(scrollBy).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
  });
});
