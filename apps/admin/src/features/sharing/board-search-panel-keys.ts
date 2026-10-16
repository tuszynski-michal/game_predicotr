export type PanelKey = { readonly linkKey: string; readonly expiresAt: string };
export type PanelKeys = Readonly<Record<string, PanelKey>>;
const STORAGE_KEY = 'game-predictor:board-search-panel-keys:v1';

function storage(): Storage | undefined {
  try {
    return typeof window === 'undefined' ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

export function loadPanelKeys(target = storage(), now = Date.now()): PanelKeys {
  try {
    const value: unknown = JSON.parse(target?.getItem(STORAGE_KEY) ?? '{}');
    if (typeof value !== 'object' || value === null) return {};
    return Object.fromEntries(
      Object.entries(value).filter(
        ([id, entry]) =>
          /^[0-9a-f-]{36}$/i.test(id) &&
          typeof entry?.linkKey === 'string' &&
          /^[A-Za-z0-9_-]{32,256}$/.test(entry.linkKey) &&
          typeof entry.expiresAt === 'string' &&
          Date.parse(entry.expiresAt) > now,
      ),
    );
  } catch {
    return {};
  }
}

export function storePanelKeys(keys: PanelKeys, target = storage()): boolean {
  try {
    if (!target) return false;
    target.setItem(STORAGE_KEY, JSON.stringify(keys));
    return true;
  } catch {
    return false;
  }
}

export function panelShareUrl(
  base: string | null,
  key: PanelKey | undefined,
): string | null {
  if (!base || !key || Date.parse(key.expiresAt) <= Date.now()) return null;
  const url = new URL(base);
  url.hash = new URLSearchParams({ key: key.linkKey }).toString();
  return url.href;
}
