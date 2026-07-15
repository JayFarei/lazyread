export type KeyValueStorage = Pick<Storage, "getItem" | "setItem">;

export function migratedStorageValue(
  storage: KeyValueStorage,
  current: string,
  ...legacy: string[]
): string | null {
  const currentValue = storage.getItem(current);
  const value = currentValue ?? legacy.map((key) => storage.getItem(key)).find((candidate) => candidate !== null) ?? null;
  if (value !== null && currentValue === null) storage.setItem(current, value);
  return value;
}
