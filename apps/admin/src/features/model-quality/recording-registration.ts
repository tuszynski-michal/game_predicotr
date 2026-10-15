import type {
  SourceRecordingCommandRequest,
  SourceRecordingGroupResponse,
} from '@game-predictor/admin-api-client';

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type RecordingRegistration = {
  readonly prepare: SourceRecordingCommandRequest;
  readonly groupId: string | null;
};
export const recordingRegistrationKey = (api: string, gameId: string) =>
  `source-recording-registration-v1:${encodeURIComponent(api)}:${gameId}`;

export function readRecordingRegistration(
  store: Store,
  api: string,
  gameId: string,
): RecordingRegistration | null {
  const raw = store.getItem(recordingRegistrationKey(api, gameId));
  if (raw === null) return null;
  const saved = JSON.parse(raw);
  if (
    saved?.api !== api ||
    saved?.gameId !== gameId ||
    saved?.registration?.prepare?.kind !== 'prepare' ||
    typeof saved.registration.prepare.idempotencyKey !== 'string' ||
    (saved.registration.groupId !== null &&
      typeof saved.registration.groupId !== 'string')
  )
    throw new Error(
      'Zapisany postęp rejestracji jest uszkodzony. Zachowano go do odzyskania.',
    );
  return saved.registration as RecordingRegistration;
}

export function saveRecordingRegistration(
  store: Store,
  api: string,
  gameId: string,
  registration: RecordingRegistration,
) {
  const current = readRecordingRegistration(store, api, gameId);
  if (
    current !== null &&
    current.prepare.idempotencyKey !== registration.prepare.idempotencyKey
  )
    throw new Error(
      'W innej karcie zapisano inną rejestrację. Nie zastąpiono jej.',
    );
  const key = recordingRegistrationKey(api, gameId);
  const raw = JSON.stringify({ api, gameId, registration });
  store.setItem(key, raw);
  if (store.getItem(key) !== raw)
    throw new Error('Nie potwierdzono trwałego zapisu postępu rejestracji.');
}

export function clearRecordingRegistration(
  store: Store,
  api: string,
  gameId: string,
  registration: RecordingRegistration,
) {
  const current = readRecordingRegistration(store, api, gameId);
  if (
    current !== null &&
    current.prepare.idempotencyKey !== registration.prepare.idempotencyKey
  )
    throw new Error(
      'Zapisana rejestracja zmieniła się w innej karcie. Zachowano nowy wpis.',
    );
  store.removeItem(recordingRegistrationKey(api, gameId));
}

export function discardRecordingRegistration(
  store: Store,
  api: string,
  gameId: string,
) {
  const key = recordingRegistrationKey(api, gameId);
  const raw = store.getItem(key);
  if (raw === null) return;
  const archiveKey = `${key}:archive:${crypto.randomUUID()}`;
  const archive = JSON.stringify({
    api,
    gameId,
    raw,
    time: new Date().toISOString(),
  });
  store.setItem(archiveKey, archive);
  if (store.getItem(archiveKey) !== archive || store.getItem(key) !== raw)
    throw new Error(
      'Nie potwierdzono archiwum postępu. Rejestrację zachowano.',
    );
  store.removeItem(key);
}

/** Never infer the next page from source totals: only the server membership ledger decides. */
export function nextRecordingMembershipCommand(
  group: SourceRecordingGroupResponse,
): SourceRecordingCommandRequest | null {
  if (
    !('nextPageIndex' in group) ||
    !('registeredPages' in group) ||
    !('createdAt' in group) ||
    !('importJobId' in group) ||
    !Number.isInteger(group.registeredPages) ||
    typeof group.createdAt !== 'string' ||
    (group.importJobId !== null && typeof group.importJobId !== 'string')
  )
    throw new Error(
      'Serwer nie zwrócił potwierdzonego postępu nagrania. Odśwież aplikację przed wznowieniem.',
    );
  if (group.membershipComplete) return null;
  const base = {
    groupId: group.id,
    expectedRevision: group.revision,
    idempotencyKey: crypto.randomUUID(),
  };
  if (group.nextPageIndex === null) return { kind: 'complete', ...base };
  if (
    !Number.isInteger(group.nextPageIndex) ||
    typeof group.nextPageIndex !== 'number' ||
    group.nextPageIndex < 0 ||
    group.nextPageIndex >= group.pageCount
  )
    throw new Error('Serwer nie wskazał poprawnej następnej partii nagrania.');
  return {
    kind: 'attach',
    ...base,
    manifestId: group.manifestId,
    pageIndex: group.nextPageIndex,
  };
}
