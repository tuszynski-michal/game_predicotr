/**
 * Access codes of board-search share links, kept only in this browser so the
 * owner can copy a code again while its link is active (D-471). The API
 * returns a code once and stores only its hash.
 */

export type BoardSearchShareCode = Readonly<{
  accessCode: string;
  expiresAt: string;
}>;

export type BoardSearchShareCodeMap = Readonly<
  Record<string, BoardSearchShareCode>
>;

type StorageLike = Pick<Storage, 'getItem' | 'removeItem' | 'setItem'>;

export const BOARD_SEARCH_SHARE_CODE_STORAGE_KEY =
  'game-predictor-board-search-share-codes-v1';

export function loadBoardSearchShareCodes(
  storage: StorageLike | null = browserStorage(),
  now = new Date(),
): BoardSearchShareCodeMap {
  if (storage === null) return {};
  try {
    const parsed: unknown = JSON.parse(
      storage.getItem(BOARD_SEARCH_SHARE_CODE_STORAGE_KEY) ?? '{}',
    );
    const codes = parseAccessCodes(parsed, now);
    persistAccessCodes(codes, storage);
    return codes;
  } catch {
    try {
      storage.removeItem(BOARD_SEARCH_SHARE_CODE_STORAGE_KEY);
    } catch {
      // An unavailable local store does not change the share link.
    }
    return {};
  }
}

export function rememberBoardSearchShareCode(
  current: BoardSearchShareCodeMap,
  input: {
    readonly accessCode: string;
    readonly expiresAt: string;
    readonly sessionId: string;
  },
  storage: StorageLike | null = browserStorage(),
  now = new Date(),
): BoardSearchShareCodeMap {
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

export function removeBoardSearchShareCode(
  current: BoardSearchShareCodeMap,
  sessionId: string,
  storage: StorageLike | null = browserStorage(),
): BoardSearchShareCodeMap {
  if (!(sessionId in current)) return current;
  const next: Record<string, BoardSearchShareCode> = { ...current };
  delete next[sessionId];
  persistAccessCodes(next, storage);
  return next;
}

export function retainActiveBoardSearchShareCodes(
  current: BoardSearchShareCodeMap,
  activeSessionIds: readonly string[],
  storage: StorageLike | null = browserStorage(),
  now = new Date(),
): BoardSearchShareCodeMap {
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

/** Forget the codes of links known to have ended (stopped, locked, expired). */
export function removeEndedBoardSearchShareCodes(
  current: BoardSearchShareCodeMap,
  endedSessionIds: readonly string[],
  storage: StorageLike | null = browserStorage(),
): BoardSearchShareCodeMap {
  const ended = new Set(endedSessionIds);
  if (!Object.keys(current).some((sessionId) => ended.has(sessionId))) {
    return current;
  }
  const next = Object.fromEntries(
    Object.entries(current).filter(([sessionId]) => !ended.has(sessionId)),
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

function parseAccessCodes(value: unknown, now: Date): BoardSearchShareCodeMap {
  if (!isRecord(value)) return {};
  const codes: Record<string, BoardSearchShareCode> = {};
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
): value is BoardSearchShareCode {
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
  codes: BoardSearchShareCodeMap,
  storage: StorageLike | null,
): void {
  if (storage === null) return;
  try {
    if (Object.keys(codes).length === 0) {
      storage.removeItem(BOARD_SEARCH_SHARE_CODE_STORAGE_KEY);
      return;
    }
    storage.setItem(BOARD_SEARCH_SHARE_CODE_STORAGE_KEY, JSON.stringify(codes));
  } catch {
    // A missing local store does not change the share link.
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
