'use client';

export interface FilenameVerificationRejectedSource {
  readonly sourceIndex: number;
  readonly sourceChecksumSha256: string;
  readonly sourceRelativePath: string;
  readonly sourceSizeBytes: number;
}

export interface FilenameVerificationPendingDecision extends FilenameVerificationRejectedSource {
  readonly expectedRevision: number;
}

export interface FilenameRangeVerificationLocalState {
  readonly runId: string;
  readonly directory: FileSystemDirectoryHandle | null;
  readonly sourceFingerprint: string;
  readonly sourceManifestChecksumSha256: string;
  readonly cursor: number;
  readonly rejectedSources: readonly FilenameVerificationRejectedSource[];
  readonly pendingDecision: FilenameVerificationPendingDecision | null;
  readonly updatedAt: string;
}

type DirectoryPermissionMode = 'read' | 'readwrite';

const DATABASE_NAME = 'game-predictor-filename-range-verification';
const DATABASE_VERSION = 1;
const STORE_NAME = 'runs';

export class FilenameRangeVerificationStore {
  private readonly factory: IDBFactory | undefined;

  constructor(factory: IDBFactory | undefined = globalThis.indexedDB) {
    this.factory = factory;
  }

  async load(
    runId: string,
  ): Promise<FilenameRangeVerificationLocalState | null> {
    if (this.factory === undefined) return null;
    const database = await this.open();
    try {
      const transaction = database.transaction(STORE_NAME, 'readonly');
      const state =
        await requestResult<FilenameRangeVerificationLocalState | null>(
          transaction.objectStore(STORE_NAME).get(runId),
        );
      return state === null
        ? null
        : { ...state, rejectedSources: state.rejectedSources ?? [] };
    } finally {
      database.close();
    }
  }

  async save(state: FilenameRangeVerificationLocalState): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).put(state);
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
          request.result.createObjectStore(STORE_NAME, { keyPath: 'runId' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(
          request.error ?? new Error('FILENAME_VERIFICATION_IDB_OPEN_FAILED'),
        );
    });
  }
}

export async function directoryPermissionIsGranted(
  directory: FileSystemDirectoryHandle,
  mode: DirectoryPermissionMode = 'read',
): Promise<boolean> {
  const permissionDirectory = directory as FileSystemDirectoryHandle & {
    queryPermission?: (options: {
      mode: DirectoryPermissionMode;
    }) => Promise<PermissionState>;
  };
  if (permissionDirectory.queryPermission === undefined) return true;
  return (await permissionDirectory.queryPermission({ mode })) === 'granted';
}

function requestResult<T>(request: IDBRequest): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve((request.result ?? null) as T);
    request.onerror = () =>
      reject(
        request.error ?? new Error('FILENAME_VERIFICATION_IDB_READ_FAILED'),
      );
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(
        transaction.error ??
          new Error('FILENAME_VERIFICATION_IDB_WRITE_ABORTED'),
      );
    transaction.onerror = () =>
      reject(
        transaction.error ??
          new Error('FILENAME_VERIFICATION_IDB_WRITE_FAILED'),
      );
  });
}
