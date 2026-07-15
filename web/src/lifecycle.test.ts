// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { CleanupScope } from "./lifecycle";

describe("CleanupScope", () => {
  it("removes document listeners when a route is disposed", () => {
    const scope = new CleanupScope();
    const listener = vi.fn();
    scope.listen(document, "keydown", listener);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "w" }));
    scope.dispose();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "w" }));

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("immediately cleans resources registered after navigation", () => {
    const scope = new CleanupScope();
    const cleanup = vi.fn();
    scope.dispose();
    scope.add(cleanup);
    expect(cleanup).toHaveBeenCalledOnce();
  });
});
