export type RemoteManualSelectionAccessCode = Readonly<{
  accessCode: string;
  expiresAt: string;
}>;

export type RemoteManualSelectionAccessCodeMap = Readonly<
  Record<string, RemoteManualSelectionAccessCode>
>;

type StorageLike = Pick<Storage, 'getItem' | 'removeItem' | 'setItem'>;

export const REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY =
  'game-predictor-remote-manual-selection-access-codes-v1';

export function loadRemoteManualSelectionAccessCodes(
  storage: StorageLike | null = browserStorage(),
  now = new Date(),
): RemoteManualSelectionAccessCodeMap {
  if (storage === null) return {};
  try {
    const parsed: unknown = JSON.parse(
      storage.getItem(REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY) ?? '{}',
    );
    const codes = parseAccessCodes(parsed, now);
    persistAccessCodes(codes, storage);
    return codes;
  } catch {
    try {
      storage.removeItem(REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY);
    } catch {
      // An unavailable local store does not change the active remote session.
    }
    return {};
  }
}

export function rememberRemoteManualSelectionAccessCode(
  current: RemoteManualSelectionAccessCodeMap,
  input: {
    readonly accessCode: string;
    readonly expiresAt: string;
    readonly sessionId: string;
  },
  storage: StorageLike | null = browserStorage(),
  now = new Date(),
): RemoteManualSelectionAccessCodeMap {
  if (!isAccessCode(input, now)) return current;
  const next = {
    ...current,
    [input.sessionId]: {
      accessCode: input.accessCode,
      expiresAt: input.expiresAt,
    },
  };
  persistAccessCodes(next, storage);
  return next;
}

export function removeRemoteManualSelectionAccessCode(
  current: RemoteManualSelectionAccessCodeMap,
  sessionId: string,
  storage: StorageLike | null = browserStorage(),
): RemoteManualSelectionAccessCodeMap {
  if (!(sessionId in current)) return current;
  const next: Record<string, RemoteManualSelectionAccessCode> = { ...current };
  delete next[sessionId];
  persistAccessCodes(next, storage);
  return next;
}

export function retainActiveRemoteManualSelectionAccessCodes(
  current: RemoteManualSelectionAccessCodeMap,
  activeSessionIds: readonly string[],
  storage: StorageLike | null = browserStorage(),
  now = new Date(),
): RemoteManualSelectionAccessCodeMap {
  const activeIds = new Set(activeSessionIds);
  const next = Object.fromEntries(
    Object.entries(current).filter(
      ([sessionId, value]) =>
        activeIds.has(sessionId) && isAccessCode(value, now),
    ),
  );
  persistAccessCodes(next, storage);
  return next;
}

function browserStorage(): StorageLike | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function parseAccessCodes(
  value: unknown,
  now: Date,
): RemoteManualSelectionAccessCodeMap {
  if (!isRecord(value)) return {};
  const codes: Record<string, RemoteManualSelectionAccessCode> = {};
  for (const [sessionId, code] of Object.entries(value)) {
    if (sessionId.trim() !== '' && isAccessCode(code, now)) {
      codes[sessionId] = code;
    }
  }
  return codes;
}

function isAccessCode(
  value: unknown,
  now: Date,
): value is RemoteManualSelectionAccessCode {
  if (!isRecord(value)) return false;
  if (
    typeof value.accessCode !== 'string' ||
    value.accessCode.trim() === '' ||
    typeof value.expiresAt !== 'string'
  ) {
    return false;
  }
  const expiresAt = Date.parse(value.expiresAt);
  return Number.isFinite(expiresAt) && expiresAt > now.getTime();
}

function persistAccessCodes(
  codes: RemoteManualSelectionAccessCodeMap,
  storage: StorageLike | null,
): void {
  if (storage === null) return;
  try {
    if (Object.keys(codes).length === 0) {
      storage.removeItem(REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY);
      return;
    }
    storage.setItem(
      REMOTE_MANUAL_SELECTION_ACCESS_CODE_STORAGE_KEY,
      JSON.stringify(codes),
    );
  } catch {
    // A missing local store does not change the active remote session.
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
