import type {
  ReadabilityItemResponse,
  ReadabilityLabelRequest,
  ReadabilityModelResponse,
} from '@game-predictor/admin-api-client';

export const READABILITY_SELECTION_LIMIT = 250;

export function canAcceptReadabilityModel(model: ReadabilityModelResponse) {
  return (
    model.status === 'completed' &&
    model.report.status === 'PASS' &&
    !model.accepted
  );
}

export function readabilityTargets(
  items: readonly ReadabilityItemResponse[],
): ReadabilityLabelRequest['targets'] {
  if (items.length === 0 || items.length > READABILITY_SELECTION_LIMIT)
    throw new Error('Wybierz od 1 do 250 pól.');
  if (items.some((item) => item.state === 'stale' || item.state === 'error'))
    throw new Error('Zmienione lub błędne pola wymagają odświeżenia.');
  return items.map((item) => ({
    cellId: item.cellId,
    expectedIdentity: item.identity,
    expectedRevision: item.revision,
  }));
}

export interface PendingReadabilityCommand {
  command: string;
  payload: unknown;
  idempotencyKey: string;
}

export function pendingReadabilityCommand(
  gameId: string,
): PendingReadabilityCommand | null {
  const saved = window.localStorage.getItem(`readability-command:${gameId}`);
  if (saved === null) return null;
  const pending: unknown = JSON.parse(saved);
  if (
    typeof pending !== 'object' ||
    pending === null ||
    !('command' in pending) ||
    typeof pending.command !== 'string' ||
    !('idempotencyKey' in pending) ||
    typeof pending.idempotencyKey !== 'string' ||
    !('payload' in pending)
  )
    throw new Error('Nie można odczytać zapisanej komendy jakości.');
  return pending as PendingReadabilityCommand;
}

/** Persist the whole intent before sending, including revisions for cold recovery. */
export function readabilityCommandKey(
  gameId: string,
  command: string,
  payload: unknown,
): string {
  const previous = pendingReadabilityCommand(gameId);
  if (previous !== null) {
    if (
      previous.command !== command ||
      JSON.stringify(previous.payload) !== JSON.stringify(payload)
    )
      throw new Error(
        'Najpierw ponów zapisaną komendę bez potwierdzonej odpowiedzi.',
      );
    return previous.idempotencyKey;
  }
  const idempotencyKey = crypto.randomUUID();
  window.localStorage.setItem(
    `readability-command:${gameId}`,
    JSON.stringify({ command, payload, idempotencyKey }),
  );
  return idempotencyKey;
}

export function completeReadabilityCommand(
  gameId: string,
  command: string,
  payload: unknown,
) {
  const pending = pendingReadabilityCommand(gameId);
  if (
    pending?.command === command &&
    JSON.stringify(pending.payload) === JSON.stringify(payload)
  )
    window.localStorage.removeItem(`readability-command:${gameId}`);
}
