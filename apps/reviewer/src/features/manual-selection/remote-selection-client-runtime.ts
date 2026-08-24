const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export const REMOTE_SELECTION_REQUEST_TIMEOUT_MS = 12_000;

interface ClientInstanceStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

interface ClientInstanceCrypto {
  getRandomValues<T extends ArrayBufferView>(array: T): T;
  randomUUID?: () => string;
}

export function readOrCreateRemoteSelectionClientInstance(
  key: string,
  storage: ClientInstanceStorage,
  cryptoSource: ClientInstanceCrypto,
): string {
  let stored: string | null = null;
  try {
    stored = storage.getItem(key);
  } catch {
    // Mobile privacy modes may expose sessionStorage but reject access.
  }
  if (stored !== null && UUID_V4.test(stored)) return stored;

  const clientInstanceId = createUuidV4(cryptoSource);
  try {
    storage.setItem(key, clientInstanceId);
  } catch {
    // The in-memory module cache remains a safe session-only fallback.
  }
  return clientInstanceId;
}

export async function fetchRemoteSelectionWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = REMOTE_SELECTION_REQUEST_TIMEOUT_MS,
  fetchImplementation: typeof fetch = globalThis.fetch,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetchImplementation.call(globalThis, input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

function createUuidV4(cryptoSource: ClientInstanceCrypto): string {
  if (typeof cryptoSource.randomUUID === 'function') {
    return cryptoSource.randomUUID.call(cryptoSource);
  }
  const bytes = cryptoSource.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0'));
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}
