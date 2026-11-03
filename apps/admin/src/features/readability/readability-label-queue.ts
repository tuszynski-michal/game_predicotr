import type { ReadabilityLabelRequest } from '@game-predictor/admin-api-client';

export const READABILITY_MAX_SELECTION = 10_000;
export const READABILITY_LABEL_BATCH_SIZE = 250;
type LabelPayload = Omit<ReadabilityLabelRequest, 'idempotencyKey'>;

export interface ReadabilityLabelQueue {
  readonly version: 1;
  readonly runId: string;
  readonly chunks: readonly ReadabilityLabelRequest[];
  readonly completed: number;
}

const storageKey = (gameId: string) => `readability-label-queue:${gameId}`;

export function loadReadabilityLabelQueue(
  gameId: string,
): ReadabilityLabelQueue | null {
  const raw = window.localStorage.getItem(storageKey(gameId));
  if (raw === null) return null;
  const queue = JSON.parse(raw) as ReadabilityLabelQueue;
  if (
    !queue ||
    queue.version !== 1 ||
    typeof queue.runId !== 'string' ||
    !Array.isArray(queue.chunks) ||
    queue.chunks.length === 0 ||
    queue.chunks.length >
      Math.ceil(READABILITY_MAX_SELECTION / READABILITY_LABEL_BATCH_SIZE) ||
    !Number.isInteger(queue.completed) ||
    queue.completed < 0 ||
    queue.completed > queue.chunks.length ||
    queue.chunks.some(
      (chunk) =>
        !chunk ||
        typeof chunk.idempotencyKey !== 'string' ||
        !Array.isArray(chunk.targets) ||
        chunk.targets.length === 0 ||
        chunk.targets.length > READABILITY_LABEL_BATCH_SIZE ||
        chunk.targets.some(
          (target: ReadabilityLabelRequest['targets'][number]) =>
            !target ||
            typeof target.cellId !== 'string' ||
            typeof target.expectedIdentity !== 'string' ||
            !Number.isInteger(target.expectedRevision),
        ),
    )
  ) {
    throw new Error('Nie można odczytać zapisanej kolejki ocen.');
  }
  return queue;
}

/** Persist every immutable target and key before the first network operation. */
export function createReadabilityLabelQueue(
  gameId: string,
  runId: string,
  payload: LabelPayload,
): ReadabilityLabelQueue {
  if (
    payload.targets.length === 0 ||
    payload.targets.length > READABILITY_MAX_SELECTION
  )
    throw new Error('Wybierz od 1 do 10 000 pól.');
  if (
    loadReadabilityLabelQueue(gameId) !== null ||
    window.localStorage.getItem(`readability-command:${gameId}`) !== null
  )
    throw new Error('Najpierw ponów zapisaną komendę lub kolejkę.');
  const chunks: ReadabilityLabelRequest[] = [];
  for (
    let index = 0;
    index < payload.targets.length;
    index += READABILITY_LABEL_BATCH_SIZE
  ) {
    chunks.push({
      ...payload,
      targets: payload.targets.slice(
        index,
        index + READABILITY_LABEL_BATCH_SIZE,
      ),
      idempotencyKey: crypto.randomUUID(),
    });
  }
  const queue: ReadabilityLabelQueue = {
    version: 1,
    runId,
    chunks,
    completed: 0,
  };
  window.localStorage.setItem(storageKey(gameId), JSON.stringify(queue));
  return loadReadabilityLabelQueue(gameId)!;
}

export function readabilityQueueProgress(queue: ReadabilityLabelQueue) {
  const total = queue.chunks.reduce(
    (count, chunk) => count + chunk.targets.length,
    0,
  );
  const done = queue.chunks
    .slice(0, queue.completed)
    .reduce((count, chunk) => count + chunk.targets.length, 0);
  return { done, remaining: total - done };
}

/** Any error pauses the tail. A missing response replays this exact chunk/key. */
export async function drainReadabilityLabelQueue(
  gameId: string,
  send: (
    runId: string,
    body: ReadabilityLabelRequest,
  ) => Promise<{ error?: unknown; data?: unknown }>,
  onProgress: (queue: ReadabilityLabelQueue | null) => void,
  active: () => boolean = () => true,
): Promise<void> {
  let queue = loadReadabilityLabelQueue(gameId);
  if (queue === null) return;
  while (queue.completed < queue.chunks.length && active()) {
    const result = await send(queue.runId, queue.chunks[queue.completed]);
    if (result.error !== undefined || result.data === undefined)
      throw new Error(
        'Zapis porcji nie został potwierdzony. Kolejka wstrzymana; ponów zapisane oceny bez zmiany rewizji.',
      );
    queue = { ...queue, completed: queue.completed + 1 };
    window.localStorage.setItem(storageKey(gameId), JSON.stringify(queue));
    onProgress(queue);
  }
  if (queue.completed === queue.chunks.length) {
    window.localStorage.removeItem(storageKey(gameId));
    onProgress(null);
  }
}

/** Explicit operator action only; confirmed server changes are never undone. */
export function discardReadabilityLabelQueue(gameId: string): void {
  window.localStorage.removeItem(storageKey(gameId));
}
