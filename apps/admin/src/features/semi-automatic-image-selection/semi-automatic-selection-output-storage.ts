'use client';

import {
  SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_FILE,
  parseSemiAutomaticSelectionOutputManifest,
  serializeSemiAutomaticSelectionOutputManifest,
  type SemiAutomaticSelectionOutputManifestV1,
} from './semi-automatic-selection-output.ts';

interface WritableOutputFile {
  abort(): Promise<void>;
  close(): Promise<void>;
  write(data: Blob | string): Promise<void>;
}

export interface SemiAutomaticOutputFileHandle {
  createWritable(): Promise<WritableOutputFile>;
  getFile(): Promise<File>;
}

interface DirectoryPermissionDescriptor {
  readonly mode: 'read' | 'readwrite';
}

export interface SemiAutomaticOutputDirectoryHandle {
  readonly name: string;
  getFileHandle(
    name: string,
    options?: { readonly create?: boolean },
  ): Promise<SemiAutomaticOutputFileHandle>;
  queryPermission?(
    descriptor: DirectoryPermissionDescriptor,
  ): Promise<PermissionState>;
  requestPermission?(
    descriptor: DirectoryPermissionDescriptor,
  ): Promise<PermissionState>;
}

export interface SemiAutomaticSourceDirectoryHandle {
  readonly name: string;
  queryPermission?(
    descriptor: DirectoryPermissionDescriptor,
  ): Promise<PermissionState>;
  requestPermission?(
    descriptor: DirectoryPermissionDescriptor,
  ): Promise<PermissionState>;
}

export interface SemiAutomaticSelectionLocalUiState {
  readonly activeExpectedIndex: number | null;
  readonly mode: 'configuration' | 'syncing_output' | 'review' | 'edit_source';
  readonly scrollLeft: number;
  readonly scrollTop: number;
  readonly zoomPercent: number;
}

export interface SemiAutomaticSelectionLocalSessionRecord {
  readonly runId: string;
  readonly sourceDirectory: SemiAutomaticSourceDirectoryHandle;
  readonly outputDirectory: SemiAutomaticOutputDirectoryHandle;
  readonly outputManifestChecksumSha256: string | null;
  readonly ui: SemiAutomaticSelectionLocalUiState;
  readonly updatedAt: string;
}

export interface SemiAutomaticSelectionLocalSessionStore {
  load(runId: string): Promise<SemiAutomaticSelectionLocalSessionRecord | null>;
  save(record: SemiAutomaticSelectionLocalSessionRecord): Promise<void>;
  remove(runId: string): Promise<void>;
}

export interface LocalOutputFileState {
  readonly checksumSha256: string;
  readonly file: File;
}

const DATABASE_NAME = 'game-predictor-semi-automatic-image-selection';
const DATABASE_VERSION = 1;
const STORE_NAME = 'sessions';

export class IndexedDbSemiAutomaticSelectionLocalSessionStore implements SemiAutomaticSelectionLocalSessionStore {
  private readonly factory: IDBFactory | undefined;

  constructor(factory: IDBFactory | undefined = globalThis.indexedDB) {
    this.factory = factory;
  }

  async load(
    runId: string,
  ): Promise<SemiAutomaticSelectionLocalSessionRecord | null> {
    if (this.factory === undefined) return null;
    const database = await openDatabase(this.factory);
    try {
      const transaction = database.transaction(STORE_NAME, 'readonly');
      const value = await requestResult(
        transaction.objectStore(STORE_NAME).get(runId),
      );
      return validateLocalSessionRecord(value);
    } finally {
      database.close();
    }
  }

  async save(record: SemiAutomaticSelectionLocalSessionRecord): Promise<void> {
    validateLocalSessionRecord(record);
    if (this.factory === undefined) return;
    const database = await openDatabase(this.factory);
    try {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).put(record);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async remove(runId: string): Promise<void> {
    if (this.factory === undefined) return;
    const database = await openDatabase(this.factory);
    try {
      const transaction = database.transaction(STORE_NAME, 'readwrite');
      transaction.objectStore(STORE_NAME).delete(runId);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }
}

export async function readSemiAutomaticSelectionOutputManifest(
  directory: SemiAutomaticOutputDirectoryHandle,
): Promise<SemiAutomaticSelectionOutputManifestV1 | null> {
  const file = await readOptionalFile(
    directory,
    SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_FILE,
  );
  return file === null
    ? null
    : parseSemiAutomaticSelectionOutputManifest(await file.text());
}

export async function writeSemiAutomaticSelectionOutputManifest(
  directory: SemiAutomaticOutputDirectoryHandle,
  manifest: SemiAutomaticSelectionOutputManifestV1,
): Promise<string> {
  const existing = await readSemiAutomaticSelectionOutputManifest(directory);
  if (existing !== null && existing.runId !== manifest.runId) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_FOREIGN');
  }
  const serialized = serializeSemiAutomaticSelectionOutputManifest(manifest);
  const handle = await directory.getFileHandle(
    SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_FILE,
    { create: true },
  );
  const writable = await handle.createWritable();
  try {
    await writable.write(serialized);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => undefined);
    throw error;
  }
  const written = await handle.getFile();
  const reparsed = parseSemiAutomaticSelectionOutputManifest(
    await written.text(),
  );
  if (
    reparsed.runId !== manifest.runId ||
    reparsed.revision !== manifest.revision
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_WRITE_INVALID');
  }
  return sha256Hex(written);
}

export async function readLocalOutputFile(
  directory: SemiAutomaticOutputDirectoryHandle,
  outputName: string,
): Promise<LocalOutputFileState | null> {
  const file = await readOptionalFile(directory, outputName);
  return file === null ? null : { checksumSha256: await sha256Hex(file), file };
}

export async function writeOriginalOutputBytes(input: {
  readonly directory: SemiAutomaticOutputDirectoryHandle;
  readonly outputName: string;
  readonly source: Blob;
  readonly expectedChecksumSha256: string;
  readonly expectedSizeBytes: number;
  readonly allowOwnedEmptyTarget?: boolean;
}): Promise<{ readonly created: boolean; readonly checksumSha256: string }> {
  if (input.source.size !== input.expectedSizeBytes) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED');
  }
  const sourceChecksum = await sha256Hex(input.source);
  if (sourceChecksum !== input.expectedChecksumSha256) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED');
  }
  const existing = await readLocalOutputFile(input.directory, input.outputName);
  if (existing !== null) {
    if (!input.allowOwnedEmptyTarget || existing.file.size !== 0) {
      if (existing.checksumSha256 !== input.expectedChecksumSha256) {
        throw new Error('SEMI_AUTOMATIC_SELECTION_TARGET_CONFLICT');
      }
      return { checksumSha256: existing.checksumSha256, created: false };
    }
  }

  const target = await input.directory.getFileHandle(input.outputName, {
    create: true,
  });
  const afterCreate = await target.getFile();
  if (afterCreate.size > 0) {
    const checksum = await sha256Hex(afterCreate);
    if (checksum !== input.expectedChecksumSha256) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_TARGET_CONFLICT');
    }
    return { checksumSha256: checksum, created: false };
  }
  const writable = await target.createWritable();
  try {
    await writable.write(input.source);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => undefined);
    throw error;
  }
  const written = await target.getFile();
  const writtenChecksum = await sha256Hex(written);
  if (
    written.size !== input.expectedSizeBytes ||
    writtenChecksum !== input.expectedChecksumSha256
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_CHECKSUM_MISMATCH');
  }
  return { checksumSha256: writtenChecksum, created: true };
}

export async function replaceOwnedOutputBytes(input: {
  readonly directory: SemiAutomaticOutputDirectoryHandle;
  readonly outputName: string;
  readonly source: Blob;
  readonly expectedChecksumSha256: string;
  readonly expectedSizeBytes: number;
  readonly expectedPreviousChecksumSha256: string | null;
}): Promise<{ readonly replaced: boolean; readonly checksumSha256: string }> {
  if (input.source.size !== input.expectedSizeBytes) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED');
  }
  const sourceChecksum = await sha256Hex(input.source);
  if (sourceChecksum !== input.expectedChecksumSha256) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED');
  }
  const existing = await readLocalOutputFile(input.directory, input.outputName);
  if (existing !== null && existing.checksumSha256 === sourceChecksum) {
    return { checksumSha256: sourceChecksum, replaced: false };
  }
  if (
    (existing === null && input.expectedPreviousChecksumSha256 !== null) ||
    (existing !== null &&
      (input.expectedPreviousChecksumSha256 === null ||
        existing.checksumSha256 !== input.expectedPreviousChecksumSha256))
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_TARGET_CONFLICT');
  }

  const target = await input.directory.getFileHandle(input.outputName, {
    create: true,
  });
  const writable = await target.createWritable();
  try {
    await writable.write(input.source);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => undefined);
    throw error;
  }
  const written = await target.getFile();
  const writtenChecksum = await sha256Hex(written);
  if (
    written.size !== input.expectedSizeBytes ||
    writtenChecksum !== input.expectedChecksumSha256
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_CHECKSUM_MISMATCH');
  }
  return { checksumSha256: writtenChecksum, replaced: existing !== null };
}

export async function restoreSemiAutomaticSelectionLocalSession(
  store: SemiAutomaticSelectionLocalSessionStore,
  runId: string,
): Promise<SemiAutomaticSelectionLocalSessionRecord | null> {
  let record: SemiAutomaticSelectionLocalSessionRecord | null;
  try {
    record = await store.load(runId);
  } catch {
    return null;
  }
  if (record === null) return null;
  const sourceGranted = await ensurePermission(record.sourceDirectory, 'read');
  if (!sourceGranted) return null;
  const outputGranted = await ensurePermission(
    record.outputDirectory,
    'readwrite',
  );
  return outputGranted ? record : null;
}

export async function sha256Hex(value: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await value.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export function validateLocalSessionRecord(
  value: unknown,
): SemiAutomaticSelectionLocalSessionRecord | null {
  if (value === null || value === undefined) return null;
  if (
    typeof value !== 'object' ||
    value === null ||
    !hasOnlyKeys(value, [
      'runId',
      'sourceDirectory',
      'outputDirectory',
      'outputManifestChecksumSha256',
      'ui',
      'updatedAt',
    ]) ||
    !('runId' in value) ||
    typeof value.runId !== 'string' ||
    value.runId.length === 0 ||
    !('sourceDirectory' in value) ||
    !isSourceDirectoryHandle(value.sourceDirectory) ||
    !('outputDirectory' in value) ||
    !isOutputDirectoryHandle(value.outputDirectory) ||
    !('outputManifestChecksumSha256' in value) ||
    (value.outputManifestChecksumSha256 !== null &&
      (typeof value.outputManifestChecksumSha256 !== 'string' ||
        !/^[0-9a-f]{64}$/u.test(value.outputManifestChecksumSha256))) ||
    !('updatedAt' in value) ||
    typeof value.updatedAt !== 'string' ||
    !Number.isFinite(Date.parse(value.updatedAt)) ||
    !('ui' in value) ||
    !isLocalUiState(value.ui)
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_LOCAL_SESSION_INVALID');
  }
  return value as SemiAutomaticSelectionLocalSessionRecord;
}

async function ensurePermission(
  handle:
    SemiAutomaticSourceDirectoryHandle | SemiAutomaticOutputDirectoryHandle,
  mode: 'read' | 'readwrite',
): Promise<boolean> {
  try {
    const descriptor = { mode } as const;
    const state =
      handle.queryPermission === undefined
        ? 'granted'
        : await handle.queryPermission(descriptor);
    if (state === 'granted') return true;
    if (state !== 'prompt' || handle.requestPermission === undefined)
      return false;
    return (await handle.requestPermission(descriptor)) === 'granted';
  } catch {
    return false;
  }
}

async function readOptionalFile(
  directory: SemiAutomaticOutputDirectoryHandle,
  name: string,
): Promise<File | null> {
  try {
    return await (await directory.getFileHandle(name)).getFile();
  } catch (error) {
    if (isNotFoundError(error)) return null;
    throw error;
  }
}

function openDatabase(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME, { keyPath: 'runId' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(
        request.error ?? new Error('SEMI_AUTOMATIC_SELECTION_IDB_OPEN_FAILED'),
      );
  });
}

function requestResult(request: IDBRequest): Promise<unknown> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result ?? null);
    request.onerror = () =>
      reject(
        request.error ?? new Error('SEMI_AUTOMATIC_SELECTION_IDB_READ_FAILED'),
      );
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(
        transaction.error ??
          new Error('SEMI_AUTOMATIC_SELECTION_IDB_WRITE_ABORTED'),
      );
    transaction.onerror = () =>
      reject(
        transaction.error ??
          new Error('SEMI_AUTOMATIC_SELECTION_IDB_WRITE_FAILED'),
      );
  });
}

function isSourceDirectoryHandle(
  value: unknown,
): value is SemiAutomaticSourceDirectoryHandle {
  return (
    typeof value === 'object' &&
    value !== null &&
    !(value instanceof Blob) &&
    'name' in value &&
    typeof value.name === 'string'
  );
}

function isOutputDirectoryHandle(
  value: unknown,
): value is SemiAutomaticOutputDirectoryHandle {
  return (
    isSourceDirectoryHandle(value) &&
    'getFileHandle' in value &&
    typeof value.getFileHandle === 'function'
  );
}

function isLocalUiState(
  value: unknown,
): value is SemiAutomaticSelectionLocalUiState {
  return (
    typeof value === 'object' &&
    value !== null &&
    hasOnlyKeys(value, [
      'activeExpectedIndex',
      'mode',
      'scrollLeft',
      'scrollTop',
      'zoomPercent',
    ]) &&
    'activeExpectedIndex' in value &&
    (value.activeExpectedIndex === null ||
      (typeof value.activeExpectedIndex === 'number' &&
        Number.isSafeInteger(value.activeExpectedIndex) &&
        value.activeExpectedIndex >= 0)) &&
    'mode' in value &&
    typeof value.mode === 'string' &&
    ['configuration', 'syncing_output', 'review', 'edit_source'].includes(
      value.mode,
    ) &&
    'scrollLeft' in value &&
    typeof value.scrollLeft === 'number' &&
    Number.isFinite(value.scrollLeft) &&
    value.scrollLeft >= 0 &&
    'scrollTop' in value &&
    typeof value.scrollTop === 'number' &&
    Number.isFinite(value.scrollTop) &&
    value.scrollTop >= 0 &&
    'zoomPercent' in value &&
    typeof value.zoomPercent === 'number' &&
    Number.isFinite(value.zoomPercent) &&
    value.zoomPercent >= 100 &&
    value.zoomPercent <= 3000
  );
}

function hasOnlyKeys(value: object, allowed: readonly string[]): boolean {
  const allowedKeys = new Set(allowed);
  return Object.keys(value).every((key) => allowedKeys.has(key));
}

function isNotFoundError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === 'NotFoundError') ||
    (typeof error === 'object' &&
      error !== null &&
      'name' in error &&
      error.name === 'NotFoundError')
  );
}
