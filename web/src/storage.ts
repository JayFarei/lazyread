export type KeyValueStorage = Pick<Storage, "getItem" | "setItem">;

export function migratedStorageValue(
  storage: KeyValueStorage,
  current: string,
  legacy: string,
): string | null {
  const currentValue = storage.getItem(current);
  const value = currentValue ?? storage.getItem(legacy);
  if (value !== null && currentValue === null) storage.setItem(current, value);
  return value;
}
