import type { GameCreate } from '@game-predictor/admin-api-client';

import type { GameDraft } from './game-catalog-state.ts';

type CommandStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function gameCreateStorageKey(apiBaseUrl: string): string {
  return `game-create-command-v1:${apiBaseUrl.replace(/\/$/, '')}`;
}

export function gameCreateCommand(draft: GameDraft, key: string): GameCreate {
  return {
    idempotencyKey: key,
    code: draft.code,
    name: draft.name,
    status: draft.status,
    expectedLayoutCount: Number(draft.expectedLayoutCount),
    superGameKind: draft.superGameKind,
    ...(draft.gridModel === undefined ? {} : { gridModel: draft.gridModel }),
  };
}

export function readPendingGameCreate(
  storage: CommandStorage,
  namespace: string,
): GameCreate | null {
  const raw = storage.getItem(namespace);
  if (raw === null) return null;
  const value: unknown = JSON.parse(raw);
  if (
    typeof value !== 'object' ||
    value === null ||
    !('schemaVersion' in value) ||
    value.schemaVersion !== 'game-create-command-v1' ||
    !('command' in value) ||
    typeof value.command !== 'object' ||
    value.command === null ||
    !('idempotencyKey' in value.command) ||
    typeof value.command.idempotencyKey !== 'string' ||
    !('code' in value.command) ||
    typeof value.command.code !== 'string' ||
    !('name' in value.command) ||
    typeof value.command.name !== 'string'
  ) {
    throw new Error(
      'Zapisane polecenie tworzenia gry jest uszkodzone. Zachowaj je do wyjaśnienia.',
    );
  }
  return value.command as GameCreate;
}

export function reserveGameCreate(
  storage: CommandStorage,
  namespace: string,
  proposed: GameCreate,
): GameCreate {
  const pending = readPendingGameCreate(storage, namespace);
  if (pending !== null) {
    if (
      JSON.stringify({
        ...pending,
        idempotencyKey: proposed.idempotencyKey,
      }) !== JSON.stringify(proposed)
    ) {
      throw new Error(
        'Dokończ poprzednie tworzenie gry. Otwórz ponownie „Nowa gra”, aby wznowić zapisane polecenie.',
      );
    }
    return pending;
  }
  storage.setItem(
    namespace,
    JSON.stringify({
      schemaVersion: 'game-create-command-v1',
      command: proposed,
    }),
  );
  // A blocked/full browser store must fail before the first POST.
  const saved = readPendingGameCreate(storage, namespace);
  if (saved === null || JSON.stringify(saved) !== JSON.stringify(proposed)) {
    throw new Error('Nie udało się trwale zapisać polecenia tworzenia gry.');
  }
  return saved;
}

export function pendingGameDraft(command: GameCreate): GameDraft {
  return {
    code: command.code,
    name: command.name,
    status: command.status ?? 'draft',
    expectedLayoutCount: String(command.expectedLayoutCount ?? 500_000),
    shapeGeometryConfiguration: 'neural_grid_v3',
    superGameKind: command.superGameKind ?? 'none',
    ...(command.gridModel === undefined
      ? {}
      : { gridModel: command.gridModel }),
  };
}

export function archivePendingCommand(
  storage: CommandStorage,
  namespace: string,
): string {
  const raw = storage.getItem(namespace);
  if (raw === null)
    throw new Error('Nie ma zapisanego polecenia do zachowania.');
  const createdAt = new Date().toISOString();
  const archiveKey = `game-command-recovery-v1:${crypto.randomUUID()}`;
  const archived = JSON.stringify({
    schemaVersion: 'game-command-recovery-v1',
    namespace,
    createdAt,
    raw,
  });
  storage.setItem(archiveKey, archived);
  if (
    storage.getItem(archiveKey) !== archived ||
    storage.getItem(namespace) !== raw
  ) {
    throw new Error('Nie potwierdzono archiwum. Zapisane polecenie pozostaje.');
  }
  storage.removeItem(namespace);
  if (storage.getItem(namespace) !== null)
    throw new Error('Zapisane polecenie pozostaje.');
  return archiveKey;
}
