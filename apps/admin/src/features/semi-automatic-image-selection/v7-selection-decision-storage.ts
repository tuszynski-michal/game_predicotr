import type { V7OutputDecisionRequest } from '@game-predictor/admin-api-client';

export interface V7SavedDecision {
  readonly runId: string;
  readonly expectedIndex: number;
  readonly body: V7OutputDecisionRequest;
  /** Local navigation intent; never changes the immutable API command. */
  readonly advanceAfterCommit?: boolean;
}

export interface V7DecisionStore {
  load(runId: string): Promise<V7SavedDecision | null>;
  save(command: V7SavedDecision): Promise<void>;
  clear(runId: string, operationId: string): Promise<void>;
}

export class IndexedDbV7DecisionStore implements V7DecisionStore {
  constructor(
    private readonly factory: IDBFactory | undefined = globalThis.indexedDB,
  ) {}

  private open(): Promise<IDBDatabase> {
    if (this.factory === undefined)
      throw new Error('V7_DECISION_STORAGE_UNAVAILABLE');
    return new Promise((resolve, reject) => {
      const request = this.factory!.open(
        'game-predictor-v7-reviewed-decisions',
        1,
      );
      request.onupgradeneeded = () =>
        request.result.createObjectStore('commands', { keyPath: 'runId' });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(request.error ?? new Error('V7_DECISION_STORAGE_UNAVAILABLE'));
      request.onblocked = () =>
        reject(new Error('V7_DECISION_STORAGE_BLOCKED'));
    });
  }

  async load(runId: string): Promise<V7SavedDecision | null> {
    const database = await this.open();
    try {
      const transaction = database.transaction('commands', 'readonly');
      const result = await idbResult(
        transaction.objectStore('commands').get(runId),
      );
      if (result === undefined || result === null) return null;
      if (
        typeof result !== 'object' ||
        !('runId' in result) ||
        result.runId !== runId ||
        !('expectedIndex' in result) ||
        !Number.isSafeInteger(result.expectedIndex) ||
        ('advanceAfterCommit' in result &&
          typeof result.advanceAfterCommit !== 'boolean') ||
        !('body' in result) ||
        typeof result.body !== 'object' ||
        result.body === null ||
        !('workflowMode' in result.body) ||
        result.body.workflowMode !== 'v7_selection' ||
        !('operationId' in result.body) ||
        typeof result.body.operationId !== 'string'
      ) {
        throw new Error('V7_DECISION_STORAGE_INVALID');
      }
      return result as V7SavedDecision;
    } finally {
      database.close();
    }
  }

  async save(command: V7SavedDecision): Promise<void> {
    const database = await this.open();
    try {
      const transaction = database.transaction('commands', 'readwrite');
      const completed = idbCompleted(transaction);
      const store = transaction.objectStore('commands');
      const current = await idbResult(store.get(command.runId));
      if (
        current !== undefined &&
        current !== null &&
        JSON.stringify(current) !== JSON.stringify(command)
      ) {
        transaction.abort();
        await completed.catch(() => undefined);
        throw new Error('V7_DECISION_ALREADY_PENDING');
      }
      store.put(command);
      await completed; // No HTTP request may precede this durable transaction completion.
    } finally {
      database.close();
    }
  }

  async clear(runId: string, operationId: string): Promise<void> {
    const database = await this.open();
    try {
      const transaction = database.transaction('commands', 'readwrite');
      const completed = idbCompleted(transaction);
      const store = transaction.objectStore('commands');
      const current = await idbResult(store.get(runId));
      if (
        typeof current === 'object' &&
        current !== null &&
        'body' in current &&
        typeof current.body === 'object' &&
        current.body !== null &&
        'operationId' in current.body &&
        current.body.operationId === operationId
      )
        store.delete(runId);
      await completed;
    } finally {
      database.close();
    }
  }
}

function idbResult(request: IDBRequest): Promise<unknown> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error('V7_DECISION_STORAGE_READ_FAILED'));
  });
}
function idbCompleted(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = transaction.onerror = () =>
      reject(
        transaction.error ?? new Error('V7_DECISION_STORAGE_WRITE_FAILED'),
      );
  });
}
