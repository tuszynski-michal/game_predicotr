'use client';

import {
  createRepairManifest,
  deriveCollectionBounds,
  finalizePendingRepairOperation,
  sortAndValidateSequenceFiles,
  validateRepairManifest,
  type ManualSelectionRepairManifest,
  type ParsedSequenceFile,
  type RepairActiveFile,
  type SequenceRange,
} from '@game-predictor/manual-image-selection-core/repair';
import type { ManualSelectionOutputManifest } from '@game-predictor/manual-image-selection-core';
import {
  readManualOutputManifest,
  sha256Hex,
} from './manual-image-selection-fsa-adapter.ts';

export const REPAIR_MANIFEST_NAME = 'manual-image-selection-repair-v1.json';

export interface RepairDirectorySnapshot {
  readonly directory: FileSystemDirectoryHandle;
  readonly files: readonly (ParsedSequenceFile & {
    readonly handle: FileSystemFileHandle;
  })[];
  readonly outputManifest: ManualSelectionOutputManifest | null;
  readonly repairManifest: ManualSelectionRepairManifest;
}

export async function inspectRepairDirectory(
  directory: FileSystemDirectoryHandle,
): Promise<RepairDirectorySnapshot> {
  const jpegEntries: Array<{
    fileName: string;
    handle: FileSystemFileHandle;
  }> = [];
  for await (const [name, handle] of directory.entries()) {
    if (handle.kind !== 'file' || !/\.jpe?g$/i.test(name)) continue;
    jpegEntries.push({ fileName: name, handle });
  }
  const parsed = sortAndValidateSequenceFiles(
    jpegEntries.map((entry) => entry.fileName),
  );
  if (parsed.length === 0) throw new Error('SEQUENCE_COLLECTION_EMPTY');
  const handles = new Map(
    jpegEntries.map((entry) => [
      entry.fileName.toLocaleLowerCase('en-US'),
      entry.handle,
    ]),
  );
  const outputManifest = await readManualOutputManifest(directory);
  const existingRepair = await readRepairManifest(directory);
  const bounds = deriveCollectionBounds({
    files: parsed,
    outputBounds: outputBounds(outputManifest),
    repairManifest: existingRepair,
  });
  const repairManifest =
    existingRepair ??
    createRepairManifest({
      bounds,
      files: parsed,
      now: new Date().toISOString(),
      repairKey: crypto.randomUUID(),
      selectedDirectoryName: directory.name,
    });
  if (repairManifest.selectedDirectoryName !== directory.name)
    throw new Error('REPAIR_DIRECTORY_CHANGED');
  return {
    directory,
    files: parsed.map((file) => ({
      ...file,
      handle: handles.get(file.fileName.toLocaleLowerCase('en-US'))!,
    })),
    outputManifest,
    repairManifest: await reconcileRepairManifest(
      directory,
      await attachVerifiedOutputChecksums(
        directory,
        repairManifest,
        outputManifest,
        parsed,
      ),
      parsed,
    ),
  };
}

export async function readRepairManifest(
  directory: FileSystemDirectoryHandle,
): Promise<ManualSelectionRepairManifest | null> {
  try {
    const file = await (
      await directory.getFileHandle(REPAIR_MANIFEST_NAME)
    ).getFile();
    return validateRepairManifest(JSON.parse(await file.text()));
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'NotFoundError')
      return null;
    throw cause;
  }
}

export async function writeRepairManifest(
  directory: FileSystemDirectoryHandle,
  manifest: ManualSelectionRepairManifest,
): Promise<void> {
  validateRepairManifest(manifest);
  const existing = await readRepairManifest(directory);
  if (existing !== null && existing.repairKey !== manifest.repairKey)
    throw new Error('FOREIGN_REPAIR_MANIFEST');
  const target = await directory.getFileHandle(REPAIR_MANIFEST_NAME, {
    create: true,
  });
  const writable = await target.createWritable();
  try {
    await writable.write(`${JSON.stringify(manifest, null, 2)}\n`);
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
}

export async function reconcileRepairManifest(
  directory: FileSystemDirectoryHandle,
  manifest: ManualSelectionRepairManifest,
  actualFiles: readonly ParsedSequenceFile[],
): Promise<ManualSelectionRepairManifest> {
  const pending = manifest.pendingOperation;
  let reconciledManifest = manifest;
  if (pending !== null) {
    const actual = actualFiles.find(
      (file) => file.fileName === pending.fileName,
    );
    if (pending.expectedFileState === 'present' && actual === undefined)
      throw new Error('REPAIR_PENDING_FILE_MISSING');
    if (pending.expectedFileState === 'absent' && actual !== undefined)
      throw new Error('REPAIR_PENDING_FILE_STILL_PRESENT');
    if (actual !== undefined) {
      const checksum = await sha256Hex(
        await (await directory.getFileHandle(actual.fileName)).getFile(),
      );
      if (checksum !== pending.checksumSha256)
        throw new Error('REPAIR_PENDING_CHECKSUM_MISMATCH');
    }
    reconciledManifest = finalizePendingRepairOperation(
      manifest,
      actual === undefined ? 'absent' : 'present',
      new Date().toISOString(),
    );
  }
  const expectedByName = new Map(
    reconciledManifest.activeFiles.map((file) => [file.fileName, file]),
  );
  const reconciled: RepairActiveFile[] = [];
  for (const file of actualFiles) {
    const expected = expectedByName.get(file.fileName);
    if (
      expected?.checksumSha256 !== null &&
      expected?.checksumSha256 !== undefined
    ) {
      const checksum = await sha256Hex(
        await (await directory.getFileHandle(file.fileName)).getFile(),
      );
      if (checksum !== expected.checksumSha256)
        throw new Error(`REPAIR_FILE_CHECKSUM_MISMATCH:${file.fileName}`);
    }
    reconciled.push({
      ...file,
      checksumSha256: expected?.checksumSha256 ?? null,
    });
  }
  return {
    ...reconciledManifest,
    activeFiles: reconciled,
    pendingOperation: null,
  };
}

async function attachVerifiedOutputChecksums(
  directory: FileSystemDirectoryHandle,
  manifest: ManualSelectionRepairManifest,
  outputManifest: ManualSelectionOutputManifest | null,
  actualFiles: readonly ParsedSequenceFile[],
): Promise<ManualSelectionRepairManifest> {
  if (outputManifest === null) return manifest;
  const outputByName = new Map(
    outputManifest.items.map((item) => [item.outputName, item]),
  );
  if (
    outputByName.size !== actualFiles.length ||
    actualFiles.some((file) => !outputByName.has(file.fileName))
  )
    throw new Error('MANUAL_OUTPUT_MANIFEST_FILES_MISMATCH');
  const activeFiles: RepairActiveFile[] = [];
  for (const file of actualFiles) {
    const output = outputByName.get(file.fileName)!;
    if (output.rangeStart !== file.start || output.rangeEnd !== file.end)
      throw new Error('MANUAL_OUTPUT_MANIFEST_RANGE_MISMATCH');
    const checksum = await sha256Hex(
      await (await directory.getFileHandle(file.fileName)).getFile(),
    );
    if (checksum !== output.imageChecksum)
      throw new Error(
        `MANUAL_OUTPUT_MANIFEST_CHECKSUM_MISMATCH:${file.fileName}`,
      );
    activeFiles.push({ ...file, checksumSha256: checksum });
  }
  return { ...manifest, activeFiles };
}

export function outputBounds(
  manifest: ManualSelectionOutputManifest | null,
): SequenceRange | null {
  if (manifest === null) return null;
  if (manifest.schemaVersion === 2 && manifest.sequenceUpperBound !== null) {
    return { end: manifest.sequenceUpperBound, start: manifest.firstLayout };
  }
  if (manifest.items.length === 0) return null;
  return {
    end: Math.max(...manifest.items.map((item) => item.rangeEnd)),
    start: manifest.firstLayout,
  };
}

export interface ManualSelectionRepairLocalState {
  readonly repairKey: string;
  readonly selectedDirectory: FileSystemDirectoryHandle;
  readonly sourceDirectory: FileSystemDirectoryHandle | null;
  readonly mode: 'fill' | 'delete' | null;
  readonly sourceCursor: number;
  readonly gapCursor: number;
  readonly fileCursor: number;
  readonly navigationStep: number;
  readonly zoom: number;
  readonly scrollTop: number;
  readonly updatedAt: string;
}

const REPAIR_DATABASE_NAME = 'game-predictor-manual-selection-repair';
const REPAIR_DATABASE_VERSION = 1;
const REPAIR_STORE = 'sessions';

export class ManualSelectionRepairStore {
  private readonly factory: IDBFactory | undefined;

  constructor(factory: IDBFactory | undefined = globalThis.indexedDB) {
    this.factory = factory;
  }

  async load(
    repairKey: string,
  ): Promise<ManualSelectionRepairLocalState | null> {
    if (this.factory === undefined) return null;
    const database = await this.open();
    try {
      const transaction = database.transaction(REPAIR_STORE, 'readonly');
      return await idbResult<ManualSelectionRepairLocalState | null>(
        transaction.objectStore(REPAIR_STORE).get(repairKey),
      );
    } finally {
      database.close();
    }
  }

  async save(state: ManualSelectionRepairLocalState): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(REPAIR_STORE, 'readwrite');
      transaction.objectStore(REPAIR_STORE).put(state);
      await idbTransaction(transaction);
    } finally {
      database.close();
    }
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = this.factory?.open(
        REPAIR_DATABASE_NAME,
        REPAIR_DATABASE_VERSION,
      );
      if (request === undefined) {
        reject(new Error('IndexedDB is unavailable.'));
        return;
      }
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(REPAIR_STORE))
          request.result.createObjectStore(REPAIR_STORE, {
            keyPath: 'repairKey',
          });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(request.error ?? new Error('IDB_OPEN_FAILED'));
    });
  }
}

function idbResult<T>(request: IDBRequest): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve((request.result ?? null) as T);
    request.onerror = () =>
      reject(request.error ?? new Error('IDB_READ_FAILED'));
  });
}

function idbTransaction(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('IDB_ABORTED'));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error('IDB_WRITE_FAILED'));
  });
}
