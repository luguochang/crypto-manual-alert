const exportStoragePrefix = "crypto-alert-v2:data-lifecycle:export";
const uuidPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

export type LifecycleStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function readPersistedExportId(
  ownerUserId: string,
  storage: LifecycleStorage,
): string | null {
  const key = exportStorageKey(ownerUserId);
  if (key === null) return null;
  try {
    const exportId = storage.getItem(key);
    if (exportId === null || uuidPattern.test(exportId)) return exportId;
    storage.removeItem(key);
  } catch {
    return null;
  }
  return null;
}

export function persistExportId(
  ownerUserId: string,
  exportId: string,
  storage: LifecycleStorage,
): boolean {
  const key = exportStorageKey(ownerUserId);
  if (key === null || !uuidPattern.test(exportId)) return false;
  try {
    storage.setItem(key, exportId);
    return true;
  } catch {
    return false;
  }
}

export function clearPersistedExportId(
  ownerUserId: string,
  storage: LifecycleStorage,
): void {
  const key = exportStorageKey(ownerUserId);
  if (key === null) return;
  try {
    storage.removeItem(key);
  } catch {
    // Browser privacy modes can deny storage access. Rejoin remains optional.
  }
}

function exportStorageKey(ownerUserId: string): string | null {
  return uuidPattern.test(ownerUserId)
    ? `${exportStoragePrefix}:${ownerUserId.toLowerCase()}`
    : null;
}
