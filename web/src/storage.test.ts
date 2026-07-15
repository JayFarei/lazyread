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
  it("prefers the Lazyreader preference over the original Listen Read key", () => {
    const storage = memoryStorage({ "lazyreader-theme": "dark", "listen-read-theme": "light" });

    expect(migratedStorageValue(storage, "lazyread-theme", "lazyreader-theme", "listen-read-theme")).toBe("dark");
    expect(storage.values.get("lazyread-theme")).toBe("dark");
  });

  it("falls back to the original Listen Read key", () => {
    const storage = memoryStorage({ "listen-read-theme": "dark" });

    expect(migratedStorageValue(storage, "lazyread-theme", "lazyreader-theme", "listen-read-theme")).toBe("dark");
  });

  it("keeps a current preference when both names exist", () => {
    const storage = memoryStorage({ "lazyread-theme": "light", "listen-read-theme": "dark" });

    expect(migratedStorageValue(storage, "lazyread-theme", "lazyreader-theme", "listen-read-theme")).toBe("light");
  });
});
