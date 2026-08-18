'use client';

import type {
  ManualSelectionSessionRecord,
  ManualSelectionTraceEvent,
} from './manual-image-selection';

const DATABASE_NAME = 'game-predictor-manual-image-selection';
const DATABASE_VERSION = 2;
const STORE_NAME = 'sessions';
const TRACE_STORE_NAME = 'traceEvents';

export class ManualImageSelectionStore {
  private readonly factory: IDBFactory | undefined;

  constructor(factory: IDBFactory | undefined = globalThis.indexedDB) {
    this.factory = factory;
  }

  async load(gameId: string): Promise<ManualSelectionSessionRecord | null> {
    if (this.factory === undefined) return null;
    const database = await this.open();
    try {
      const transaction = database.transaction(STORE_NAME, 'readonly');
      return (await requestResult(
        transaction.objectStore(STORE_NAME).get(gameId),
      )) as ManualSelectionSessionRecord | null;
    } finally {
      database.close();
    }
  }

  async save(record: ManualSelectionSessionRecord): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).put(record);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async clear(gameId: string): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      // Keep every asynchronous IDB request inside its own transaction. A
      // read request can yield control long enough for a readwrite
      // transaction to become inactive in Chromium/Firefox.
      const readTransaction = database.transaction(TRACE_STORE_NAME, 'readonly');
      const traceKeys = await requestAllKeys(
        readTransaction.objectStore(TRACE_STORE_NAME),
      );

      const writeTransaction = database.transaction(
        [STORE_NAME, TRACE_STORE_NAME],
        'readwrite',
      );
      writeTransaction.objectStore(STORE_NAME).delete(gameId);
      const traceStore = writeTransaction.objectStore(TRACE_STORE_NAME);
      for (const key of traceKeys) {
        if (Array.isArray(key) && key[0] === gameId) traceStore.delete(key);
      }
      await transactionComplete(writeTransaction);
    } finally {
      database.close();
    }
  }

  async appendTraceEvent(event: ManualSelectionTraceEvent): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(TRACE_STORE_NAME, 'readwrite');
      transaction.objectStore(TRACE_STORE_NAME).put(event);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async loadTraceEvents(
    gameId: string,
    sessionKey: string,
  ): Promise<ManualSelectionTraceEvent[]> {
    if (this.factory === undefined) return [];
    const database = await this.open();
    try {
      const transaction = database.transaction(TRACE_STORE_NAME, 'readonly');
      const records = (await requestAll(
        transaction.objectStore(TRACE_STORE_NAME),
      )) as ManualSelectionTraceEvent[];
      return records
        .filter(
          (event) => event.gameId === gameId && event.sessionKey === sessionKey,
        )
        .sort((left, right) => left.eventIndex - right.eventIndex);
    } finally {
      database.close();
    }
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = this.factory?.open(DATABASE_NAME, DATABASE_VERSION);
      if (request === undefined) {
        reject(new Error('IndexedDB is unavailable.'));
        return;
      }
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) {
          request.result.createObjectStore(STORE_NAME, { keyPath: 'gameId' });
        }
        if (!request.result.objectStoreNames.contains(TRACE_STORE_NAME)) {
          request.result.createObjectStore(TRACE_STORE_NAME, {
            keyPath: ['gameId', 'sessionKey', 'eventIndex'],
          });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(request.error ?? new Error('IDB_OPEN_FAILED'));
    });
  }
}

function requestResult(request: IDBRequest): Promise<unknown> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result ?? null);
    request.onerror = () =>
      reject(request.error ?? new Error('IDB_READ_FAILED'));
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('IDB_ABORTED'));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error('IDB_WRITE_FAILED'));
  });
}

function requestAll(store: IDBObjectStore): Promise<unknown[]> {
  return new Promise((resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error('IDB_READ_FAILED'));
  });
}

function requestAllKeys(store: IDBObjectStore): Promise<IDBValidKey[]> {
  return new Promise((resolve, reject) => {
    const request = store.getAllKeys();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error('IDB_READ_FAILED'));
  });
}
