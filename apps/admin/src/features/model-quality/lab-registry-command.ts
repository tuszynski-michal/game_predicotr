import type {
  ImportLabSymbolCandidateCommand,
  SymbolModelDeactivationCommand,
} from '@game-predictor/admin-api-client';

export type PendingLabRegistryCommand =
  | {
      readonly kind: 'import';
      readonly gameId: string;
      readonly body: ImportLabSymbolCandidateCommand;
    }
  | {
      readonly kind: 'deactivate';
      readonly gameId: string;
      readonly body: SymbolModelDeactivationCommand;
    };

type CommandStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const key = (gameId: string) => `model-registry-command-v1:${gameId}`;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function readPendingLabRegistryCommand(
  storage: CommandStorage,
  gameId: string,
): PendingLabRegistryCommand | null {
  const raw = storage.getItem(key(gameId));
  if (raw === null) return null;
  const command: unknown = JSON.parse(raw);
  if (
    typeof command !== 'object' ||
    command === null ||
    !('gameId' in command) ||
    command.gameId !== gameId ||
    !('kind' in command) ||
    !('body' in command) ||
    typeof command.body !== 'object' ||
    command.body === null ||
    !('idempotencyKey' in command.body) ||
    typeof command.body.idempotencyKey !== 'string' ||
    !uuid.test(command.body.idempotencyKey)
  ) {
    throw new Error('Zapisana operacja modelu jest nieprawidłowa.');
  }
  if (
    command.kind === 'import' &&
    'candidateFingerprint' in command.body &&
    typeof command.body.candidateFingerprint === 'string' &&
    /^[0-9a-f]{64}$/.test(command.body.candidateFingerprint)
  ) {
    return command as PendingLabRegistryCommand;
  }
  if (
    command.kind === 'deactivate' &&
    'expectedCurrentModelIterationId' in command.body &&
    typeof command.body.expectedCurrentModelIterationId === 'string' &&
    uuid.test(command.body.expectedCurrentModelIterationId) &&
    'actor' in command.body &&
    typeof command.body.actor === 'string'
  ) {
    return command as PendingLabRegistryCommand;
  }
  throw new Error('Zapisana operacja modelu jest nieprawidłowa.');
}

export function saveLabRegistryCommand(
  storage: CommandStorage,
  command: PendingLabRegistryCommand,
): PendingLabRegistryCommand {
  const pending = readPendingLabRegistryCommand(storage, command.gameId);
  if (pending !== null) return pending;
  storage.setItem(key(command.gameId), JSON.stringify(command));
  return command;
}

export function clearLabRegistryCommand(
  storage: CommandStorage,
  gameId: string,
): void {
  storage.removeItem(key(gameId));
}

export function reconcileLabRegistryFailure(
  storage: CommandStorage,
  gameId: string,
  status: number,
): boolean {
  // Domain refusals permit a fresh preview. Authentication can fail before
  // receipt lookup, so preserve the command until authorization is restored.
  if (![404, 409, 422].includes(status)) return false;
  clearLabRegistryCommand(storage, gameId);
  return true;
}
