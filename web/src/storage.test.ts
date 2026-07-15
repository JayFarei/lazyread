import { describe, expect, it } from "vitest";
import { migratedStorageValue } from "./storage";

function memoryStorage(entries: Record<string, string> = {}) {
  const values = new Map(Object.entries(entries));
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    values,
  };
}

describe("migratedStorageValue", () => {
  it("copies a legacy preference into the Lazyreader key", () => {
    const storage = memoryStorage({ "listen-read-theme": "dark" });

    expect(migratedStorageValue(storage, "lazyreader-theme", "listen-read-theme")).toBe("dark");
    expect(storage.values.get("lazyreader-theme")).toBe("dark");
  });

  it("keeps a current preference when both names exist", () => {
    const storage = memoryStorage({ "lazyreader-theme": "light", "listen-read-theme": "dark" });

    expect(migratedStorageValue(storage, "lazyreader-theme", "listen-read-theme")).toBe("light");
  });
});
