'use client';

interface WritableOutputFile {
  abort(): Promise<void>;
  close(): Promise<void>;
  write(data: Blob): Promise<void>;
}

export interface OutputFileHandle {
  createWritable(): Promise<WritableOutputFile>;
  getFile(): Promise<File>;
}

interface DirectoryPermissionDescriptor {
  readonly mode: 'readwrite';
}

export interface OutputDirectoryHandle {
  readonly name?: string;
  getFileHandle(
    name: string,
    options?: { readonly create?: boolean },
  ): Promise<OutputFileHandle>;
  queryPermission?(
    descriptor: DirectoryPermissionDescriptor,
  ): Promise<PermissionState>;
  requestPermission?(
    descriptor: DirectoryPermissionDescriptor,
  ): Promise<PermissionState>;
}

export interface OutputDirectoryStore {
  load(gameId: string, runId: string): Promise<OutputDirectoryHandle | null>;
  save(
    gameId: string,
    runId: string,
    directory: OutputDirectoryHandle,
  ): Promise<void>;
}

const DATABASE_NAME = 'game-predictor-admin';
const DATABASE_VERSION = 1;
const STORE_NAME = 'image-selection-output-directories';

export class IndexedDbOutputDirectoryStore implements OutputDirectoryStore {
  private readonly factory: IDBFactory | undefined;

  constructor(factory: IDBFactory | undefined = globalThis.indexedDB) {
    this.factory = factory;
  }

  async load(
    gameId: string,
    runId: string,
  ): Promise<OutputDirectoryHandle | null> {
    if (this.factory === undefined) return null;
    const database = await openDatabase(this.factory);
    try {
      const transaction = database.transaction(STORE_NAME, 'readonly');
      const value = await requestResult(
        transaction.objectStore(STORE_NAME).get(storageKey(gameId, runId)),
      );
      return isOutputDirectoryHandle(value) ? value : null;
    } finally {
      database.close();
    }
  }

  async save(
    gameId: string,
    runId: string,
    directory: OutputDirectoryHandle,
  ): Promise<void> {
    if (this.factory === undefined) return;
    const database = await openDatabase(this.factory);
    try {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).put({
        directory,
        key: storageKey(gameId, runId),
      });
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }
}

export async function restoreOutputDirectory(
  store: OutputDirectoryStore,
  gameId: string,
  runId: string,
): Promise<OutputDirectoryHandle | null> {
  let directory: OutputDirectoryHandle | null;
  try {
    directory = await store.load(gameId, runId);
  } catch {
    return null;
  }
  if (directory === null) return null;
  try {
    const descriptor = { mode: 'readwrite' } as const;
    const permission =
      directory.queryPermission === undefined
        ? 'granted'
        : await directory.queryPermission(descriptor);
    if (permission === 'granted') return directory;
    if (permission !== 'prompt' || directory.requestPermission === undefined) {
      return null;
    }
    return (await directory.requestPermission(descriptor)) === 'granted'
      ? directory
      : null;
  } catch {
    return null;
  }
}

function openDatabase(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error('IDB_OPEN_FAILED'));
  });
}

function requestResult(request: IDBRequest): Promise<unknown> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => {
      const record = request.result as { readonly directory?: unknown } | null;
      resolve(record?.directory ?? null);
    };
    request.onerror = () =>
      reject(request.error ?? new Error('IDB_READ_FAILED'));
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('IDB_WRITE_ABORTED'));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error('IDB_WRITE_FAILED'));
  });
}

function storageKey(gameId: string, runId: string): string {
  return `${gameId}:${runId}`;
}

function isOutputDirectoryHandle(
  value: unknown,
): value is OutputDirectoryHandle {
  return (
    typeof value === 'object' &&
    value !== null &&
    'getFileHandle' in value &&
    typeof value.getFileHandle === 'function'
  );
}
