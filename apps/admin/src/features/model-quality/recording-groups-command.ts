import type { SourceRecordingCommandRequest } from '@game-predictor/admin-api-client';

type CommandStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export const recordingCommandKey = (api: string, gameId: string) =>
  `source-recording-command-v1:${encodeURIComponent(api)}:${gameId}`;

export function readRecordingCommand(
  storage: CommandStorage,
  api: string,
  gameId: string,
): SourceRecordingCommandRequest | null {
  const raw = storage.getItem(recordingCommandKey(api, gameId));
  if (raw === null) return null;
  const saved = JSON.parse(raw);
  if (
    saved?.api !== api ||
    saved?.gameId !== gameId ||
    saved?.version !== 1 ||
    typeof saved.command !== 'object' ||
    saved.command === null ||
    ![
      'prepare',
      'attach',
      'complete',
      'declare',
      'assign_role',
      'retract',
      'alias',
      'freeze',
    ].includes(saved.command.kind) ||
    !Number.isInteger(saved.command.expectedRevision) ||
    saved.command.expectedRevision < 0 ||
    typeof saved.command.idempotencyKey !== 'string' ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      saved.command.idempotencyKey,
    )
  ) {
    throw new Error(
      'Zapisane polecenie nagrania jest uszkodzone. Zachowano je do jawnego porzucenia.',
    );
  }
  return saved.command as SourceRecordingCommandRequest;
}

/** Persist and re-read the exact JSON before any request can leave the browser. */
export function reserveRecordingCommand(
  storage: CommandStorage,
  api: string,
  gameId: string,
  command: SourceRecordingCommandRequest,
): SourceRecordingCommandRequest {
  const namespace = recordingCommandKey(api, gameId);
  if (storage.getItem(namespace) !== null) {
    throw new Error('Najpierw ponów albo porzuć zapisane polecenie nagrania.');
  }
  const raw = JSON.stringify({ version: 1, api, gameId, command });
  storage.setItem(namespace, raw);
  if (storage.getItem(namespace) !== raw) {
    throw new Error(
      'Nie potwierdzono trwałego zapisu polecenia. Nie wysłano żądania.',
    );
  }
  return readRecordingCommand(storage, api, gameId)!;
}

/** Clear only the exact confirmed command, without deleting a newer tab's intent. */
export function completeRecordingCommand(
  storage: CommandStorage,
  api: string,
  gameId: string,
  command: SourceRecordingCommandRequest,
): void {
  const current = readRecordingCommand(storage, api, gameId);
  if (current !== null && JSON.stringify(current) === JSON.stringify(command)) {
    storage.removeItem(recordingCommandKey(api, gameId));
  }
}

export function discardRecordingCommand(
  storage: CommandStorage,
  api: string,
  gameId: string,
  confirmed: boolean,
): void {
  if (!confirmed) return;
  const namespace = recordingCommandKey(api, gameId);
  const raw = storage.getItem(namespace);
  if (raw === null) return;
  const archiveKey = `${namespace}:archive:${crypto.randomUUID()}`;
  const archive = JSON.stringify({
    api,
    gameId,
    namespace,
    raw,
    time: new Date().toISOString(),
  });
  storage.setItem(archiveKey, archive);
  if (storage.getItem(archiveKey) !== archive) {
    throw new Error(
      'Nie potwierdzono trwałego zapisu archiwum. Polecenie zachowano.',
    );
  }
  // Preserve a newer entry written by another tab while archiving this one.
  if (storage.getItem(namespace) !== raw) {
    throw new Error(
      'Polecenie zmieniło się w innej karcie. Nie usunięto nowego wpisu.',
    );
  }
  storage.removeItem(namespace);
}
