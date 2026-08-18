'use client';

import type { ManualSelectionSessionRecord } from './manual-image-selection';

const DATABASE_NAME = 'game-predictor-manual-image-selection';
const DATABASE_VERSION = 1;
const STORE_NAME = 'sessions';

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
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).delete(gameId);
      await transactionComplete(transaction);
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
