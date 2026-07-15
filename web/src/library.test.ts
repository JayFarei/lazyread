// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { LibraryProgressStreams, newArticleDialogMarkup } from "./library";
import type { Article } from "./types";

const article = (id: string, status: Article["status"]): Article => ({
  id,
  status,
  title: id,
  route: `/read/${id}`,
  warnings: [],
});

describe("LibraryProgressStreams", () => {
  it("starts after retry or restore and stops on terminal updates", () => {
    const streams: Array<{ id: string; open: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn>; update: (article: Article) => void }> = [];
    const updates: Article[] = [];
    const manager = new LibraryProgressStreams(
      (update) => updates.push(update),
      (id, update) => {
        const stream = { id, open: vi.fn(), close: vi.fn(), update };
        streams.push(stream);
        return stream;
      },
    );

    manager.sync([article("retry", "failed"), article("restore", "trashed")]);
    expect(streams).toHaveLength(0);

    manager.sync([article("retry", "processing"), article("restore", "processing")]);
    expect(streams.map((stream) => stream.id)).toEqual(["retry", "restore"]);
    expect(streams.every((stream) => stream.open.mock.calls.length === 1)).toBe(true);

    streams[0]!.update(article("retry", "ready"));
    expect(streams[0]!.close).toHaveBeenCalledOnce();
    expect(updates.at(-1)?.status).toBe("ready");

    manager.sync([article("retry", "ready"), article("restore", "trashed")]);
    expect(streams[1]!.close).toHaveBeenCalledOnce();

    manager.close();
    expect(streams[0]!.close).toHaveBeenCalledOnce();
    expect(streams[1]!.close).toHaveBeenCalledOnce();
  });
});

describe("newArticleDialogMarkup", () => {
  it("labels the modal with its visible heading", () => {
    document.body.innerHTML = newArticleDialogMarkup("close");
    const dialog = document.querySelector("dialog")!;
    const label = document.getElementById(dialog.getAttribute("aria-labelledby")!);
    expect(label?.textContent).toBe("New listening article");
  });
});
