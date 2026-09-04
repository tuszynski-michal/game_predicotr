'use client';

const DATABASE_NAME = 'game-predictor-selected-image-crop';
const DATABASE_VERSION = 1;
const STORE_NAME = 'sessions';
const SESSION_KEY = 'local-selected-image-crop-v1';

export interface SelectedImageCropLocalSession {
  readonly key: typeof SESSION_KEY;
  readonly parentDirectory: FileSystemDirectoryHandle;
  readonly sourceDirectoryName: string;
  readonly currentIndex: number;
  readonly zoom: number;
  readonly scrollLeft: number;
  readonly scrollTop: number;
  readonly updatedAt: string;
}

export class SelectedImageCropLocalStore {
  constructor(
    private readonly factory: IDBFactory | undefined = globalThis.indexedDB,
  ) {}

  async load(): Promise<SelectedImageCropLocalSession | null> {
    if (this.factory === undefined) return null;
    const database = await this.open();
    try {
      const transaction = database.transaction(STORE_NAME, 'readonly');
      return (await requestResult(
        transaction.objectStore(STORE_NAME).get(SESSION_KEY),
      )) as SelectedImageCropLocalSession | null;
    } finally {
      database.close();
    }
  }

  async save(
    session: Omit<SelectedImageCropLocalSession, 'key'>,
  ): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).put({ ...session, key: SESSION_KEY });
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async clear(): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).delete(SESSION_KEY);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = this.factory?.open(DATABASE_NAME, DATABASE_VERSION);
      if (request === undefined) {
        reject(new Error('SELECTED_IMAGE_CROP_INDEXED_DB_UNAVAILABLE'));
        return;
      }
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) {
          request.result.createObjectStore(STORE_NAME, { keyPath: 'key' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(
          request.error ?? new Error('SELECTED_IMAGE_CROP_IDB_OPEN_FAILED'),
        );
    });
  }
}

function requestResult(request: IDBRequest): Promise<unknown> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result ?? null);
    request.onerror = () =>
      reject(request.error ?? new Error('SELECTED_IMAGE_CROP_IDB_READ_FAILED'));
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('SELECTED_IMAGE_CROP_IDB_ABORTED'));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error('SELECTED_IMAGE_CROP_IDB_FAILED'));
  });
}
