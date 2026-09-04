'use client';

import {
  createRepairManifest,
  deriveFilledGapsManifest,
  deriveCollectionBounds,
  finalizePendingRepairOperation,
  findSequenceGaps,
  sortAndValidateSequenceFiles,
  validateRepairManifest,
  validateFilledGapsManifest,
  type ManualSelectionFilledGapsManifest,
  type ManualSelectionRepairManifest,
  type ParsedSequenceFile,
  type RepairActiveFile,
  type RepairOperationKind,
  type SequenceRange,
} from '@game-predictor/manual-image-selection-core/repair';
import type { ManualSelectionOutputManifest } from '@game-predictor/manual-image-selection-core';
import {
  readManualOutputManifest,
  sha256Hex,
} from './manual-image-selection-fsa-adapter.ts';

export const REPAIR_MANIFEST_NAME = 'manual-image-selection-repair-v1.json';
export const REPAIR_TRACE_NAME = 'manual-image-selection-repair-trace-v1.json';
export const FILLED_GAPS_MANIFEST_NAME =
  'manual-image-selection-filled-gaps-v1.json';

export interface ManualSelectionRepairTraceEvent {
  readonly eventIndex: number;
  readonly kind: 'viewed' | 'fill' | 'undo_fill' | 'delete' | 'restore';
  readonly repairKey: string;
  readonly sourcePath: string | null;
  readonly sourceIndex: number | null;
  readonly rangeStart: number;
  readonly rangeEnd: number;
  readonly imageChecksum: string | null;
  readonly outputName: string | null;
  readonly decoded: boolean;
  readonly visibleMilliseconds: number;
  readonly recordedAt: string;
}

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
  const reconciled = await reconcileRepairManifest(
    directory,
    repairManifest,
    parsed,
  );
  return {
    directory,
    files: parsed.map((file) => ({
      ...file,
      handle: handles.get(file.fileName.toLocaleLowerCase('en-US'))!,
    })),
    outputManifest,
    repairManifest: await attachVerifiedOutputChecksums(
      directory,
      reconciled,
      outputManifest,
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
  await writeJsonFile(
    directory,
    FILLED_GAPS_MANIFEST_NAME,
    deriveFilledGapsManifest(manifest),
  );
}

export async function readActiveFilledGapsManifest(
  directory: FileSystemDirectoryHandle,
): Promise<ManualSelectionFilledGapsManifest | null> {
  const repair = await readRepairManifest(directory);
  if (repair === null) return null;
  const derived = deriveFilledGapsManifest(repair);
  try {
    const file = await (
      await directory.getFileHandle(FILLED_GAPS_MANIFEST_NAME)
    ).getFile();
    const stored = validateFilledGapsManifest(JSON.parse(await file.text()));
    if (
      stored.repairKey !== derived.repairKey ||
      stored.selectedDirectoryName !== derived.selectedDirectoryName ||
      stored.repairRevision !== derived.repairRevision
    )
      return derived;
    return stored;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'NotFoundError')
      return derived;
    throw cause;
  }
}

export async function appendRepairTraceEvent(
  directory: FileSystemDirectoryHandle,
  repairKey: string,
  event: ManualSelectionRepairTraceEvent,
): Promise<void> {
  let events: ManualSelectionRepairTraceEvent[] = [];
  try {
    const file = await (
      await directory.getFileHandle(REPAIR_TRACE_NAME)
    ).getFile();
    const parsed: unknown = JSON.parse(await file.text());
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      !('schemaVersion' in parsed) ||
      parsed.schemaVersion !== 'manual-image-selection-repair-trace-v1' ||
      !('repairKey' in parsed) ||
      parsed.repairKey !== repairKey ||
      !('events' in parsed) ||
      !Array.isArray(parsed.events)
    )
      throw new Error('INVALID_REPAIR_TRACE');
    events = parsed.events as ManualSelectionRepairTraceEvent[];
  } catch (cause) {
    if (!(cause instanceof DOMException && cause.name === 'NotFoundError'))
      throw cause;
  }
  await writeJsonFile(directory, REPAIR_TRACE_NAME, {
    events: [...events, event],
    repairKey,
    schemaVersion: 'manual-image-selection-repair-trace-v1',
    updatedAt: event.recordedAt,
  });
}

export async function writeRepairFile(input: {
  readonly directory: FileSystemDirectoryHandle;
  readonly manifest: ManualSelectionRepairManifest;
  readonly outputManifest: ManualSelectionOutputManifest | null;
  readonly source: FileSystemFileHandle;
  readonly sourcePath: string;
  readonly sourceIndex: number | null;
  readonly target: SequenceRange;
  readonly kind: 'fill' | 'restore';
}): Promise<{
  readonly fileHandle: FileSystemFileHandle;
  readonly manifest: ManualSelectionRepairManifest;
  readonly outputManifest: ManualSelectionOutputManifest | null;
}> {
  const fileName = `seq_${input.target.start}-${input.target.end}.jpg`;
  if (await fileExists(input.directory, fileName))
    throw new Error(`REPAIR_TARGET_ALREADY_EXISTS:${fileName}`);
  const sourceFile = await input.source.getFile();
  const checksumSha256 = await sha256Hex(sourceFile);
  const pendingOperation = repairOperation({
    checksumSha256,
    expectedFileState: 'present',
    fileName,
    kind: input.kind,
    sourceIndex: input.sourceIndex,
    sourcePath: input.sourcePath,
    target: input.target,
  });
  await writeRepairManifest(input.directory, {
    ...input.manifest,
    pendingOperation,
  });
  const target = await input.directory.getFileHandle(fileName, {
    create: true,
  });
  const writable = await target.createWritable();
  try {
    await writable.write(sourceFile);
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
  if ((await sha256Hex(await target.getFile())) !== checksumSha256)
    throw new Error(`REPAIR_WRITTEN_CHECKSUM_MISMATCH:${fileName}`);
  const completed = finalizePendingRepairOperation(
    { ...input.manifest, pendingOperation },
    'present',
    new Date().toISOString(),
  );
  await writeRepairManifest(input.directory, completed);
  const outputManifest = await synchronizeOutputManifest(
    input.directory,
    input.outputManifest,
    completed,
  );
  return { fileHandle: target, manifest: completed, outputManifest };
}

export async function deleteRepairFile(input: {
  readonly directory: FileSystemDirectoryHandle;
  readonly manifest: ManualSelectionRepairManifest;
  readonly outputManifest: ManualSelectionOutputManifest | null;
  readonly fileName: string;
  readonly expectedChecksumSha256?: string;
  readonly kind: 'delete' | 'undo_fill';
  readonly sourceIndex: number | null;
  readonly sourcePath: string | null;
}): Promise<{
  readonly file: File;
  readonly manifest: ManualSelectionRepairManifest;
  readonly outputManifest: ManualSelectionOutputManifest | null;
}> {
  const parsed = sortAndValidateSequenceFiles([input.fileName])[0]!;
  const handle = await input.directory.getFileHandle(input.fileName);
  const file = await handle.getFile();
  const checksumSha256 = await sha256Hex(file);
  const expected = input.manifest.activeFiles.find(
    (active) => active.fileName === input.fileName,
  );
  if (expected === undefined) throw new Error('REPAIR_FILE_NOT_MANAGED');
  if (
    expected.checksumSha256 !== null &&
    expected.checksumSha256 !== checksumSha256
  )
    throw new Error(`REPAIR_FILE_CHECKSUM_MISMATCH:${input.fileName}`);
  if (
    input.expectedChecksumSha256 !== undefined &&
    input.expectedChecksumSha256 !== checksumSha256
  )
    throw new Error(`REPAIR_FILE_CHECKSUM_MISMATCH:${input.fileName}`);
  const pendingOperation = repairOperation({
    checksumSha256,
    expectedFileState: 'absent',
    fileName: input.fileName,
    kind: input.kind,
    sourceIndex: input.sourceIndex,
    sourcePath: input.sourcePath,
    target: parsed,
  });
  await writeRepairManifest(input.directory, {
    ...input.manifest,
    pendingOperation,
  });
  await input.directory.removeEntry(input.fileName);
  const completed = finalizePendingRepairOperation(
    { ...input.manifest, pendingOperation },
    'absent',
    new Date().toISOString(),
  );
  await writeRepairManifest(input.directory, completed);
  const outputManifest = await synchronizeOutputManifest(
    input.directory,
    input.outputManifest,
    completed,
  );
  return { file, manifest: completed, outputManifest };
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
  const verifiedByName = new Map(
    manifest.activeFiles.map((file) => [file.fileName, file.checksumSha256]),
  );
  const activeFiles: RepairActiveFile[] = [];
  for (const file of actualFiles) {
    const output = outputByName.get(file.fileName)!;
    if (output.rangeStart !== file.start || output.rangeEnd !== file.end)
      throw new Error('MANUAL_OUTPUT_MANIFEST_RANGE_MISMATCH');
    // `reconcileRepairManifest` has already read and verified a known checksum
    // during this inspection. Reusing it prevents a second complete Blob read
    // for every JPEG while preserving the full reload verification contract.
    const verifiedChecksum = verifiedByName.get(file.fileName);
    const checksum =
      verifiedChecksum ??
      (await sha256Hex(
        await (await directory.getFileHandle(file.fileName)).getFile(),
      ));
    if (checksum !== output.imageChecksum)
      throw new Error(
        `MANUAL_OUTPUT_MANIFEST_CHECKSUM_MISMATCH:${file.fileName}`,
      );
    activeFiles.push({ ...file, checksumSha256: checksum });
  }
  return { ...manifest, activeFiles };
}

async function synchronizeOutputManifest(
  directory: FileSystemDirectoryHandle,
  original: ManualSelectionOutputManifest | null,
  repair: ManualSelectionRepairManifest,
): Promise<ManualSelectionOutputManifest | null> {
  if (original === null) return null;
  const originalItems = new Map(
    original.items.map((item) => [item.outputName, item]),
  );
  const operations = new Map<string, (typeof repair.operations)[number]>();
  for (const operation of repair.operations)
    operations.set(operation.fileName, operation);
  const items = repair.activeFiles.map((file) => {
    const originalItem = originalItems.get(file.fileName);
    const operation = operations.get(file.fileName);
    const checksum = file.checksumSha256 ?? originalItem?.imageChecksum;
    const imagePath = operation?.sourcePath ?? originalItem?.imagePath;
    if (checksum === undefined || imagePath === undefined || imagePath === null)
      throw new Error(`REPAIR_OUTPUT_PROVENANCE_MISSING:${file.fileName}`);
    return {
      activeBoardCount: file.end - file.start + 1,
      imageChecksum: checksum,
      imagePath,
      outputName: file.fileName,
      rangeEnd: file.end,
      rangeStart: file.start,
    };
  });
  const gaps = findSequenceGaps(
    { end: repair.collectionEnd, start: repair.collectionStart },
    repair.activeFiles,
    repair.deletedRanges,
  );
  const nextManifest: ManualSelectionOutputManifest = {
    direction: original.direction,
    firstLayout: original.firstLayout,
    gameId: original.gameId,
    items,
    schemaVersion: 2,
    selectionComplete: gaps.length === 0,
    sequenceUpperBound: repair.collectionEnd,
    sessionKey: original.sessionKey,
    sourceDirectoryName: original.sourceDirectoryName,
    updatedAt: new Date().toISOString(),
  };
  await writeJsonFile(
    directory,
    'manual-image-selection-output-v1.json',
    nextManifest,
  );
  return nextManifest;
}

function repairOperation(input: {
  readonly checksumSha256: string;
  readonly expectedFileState: 'absent' | 'present';
  readonly fileName: string;
  readonly kind: RepairOperationKind;
  readonly sourceIndex: number | null;
  readonly sourcePath: string | null;
  readonly target: SequenceRange;
}) {
  return {
    checksumSha256: input.checksumSha256,
    expectedFileState: input.expectedFileState,
    fileName: input.fileName,
    id: crypto.randomUUID(),
    kind: input.kind,
    occurredAt: new Date().toISOString(),
    rangeEnd: input.target.end,
    rangeStart: input.target.start,
    sourceIndex: input.sourceIndex,
    sourcePath: input.sourcePath,
  } as const;
}

async function writeJsonFile(
  directory: FileSystemDirectoryHandle,
  name: string,
  value: object,
): Promise<void> {
  const target = await directory.getFileHandle(name, { create: true });
  const writable = await target.createWritable();
  try {
    await writable.write(`${JSON.stringify(value, null, 2)}\n`);
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
}

async function fileExists(
  directory: FileSystemDirectoryHandle,
  name: string,
): Promise<boolean> {
  try {
    await directory.getFileHandle(name);
    return true;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'NotFoundError')
      return false;
    throw cause;
  }
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

  async loadLatest(): Promise<ManualSelectionRepairLocalState | null> {
    if (this.factory === undefined) return null;
    const database = await this.open();
    try {
      const transaction = database.transaction(REPAIR_STORE, 'readonly');
      const states = await idbResult<ManualSelectionRepairLocalState[]>(
        transaction.objectStore(REPAIR_STORE).getAll(),
      );
      return (
        states.sort(
          (left, right) =>
            Date.parse(right.updatedAt) - Date.parse(left.updatedAt) ||
            left.repairKey.localeCompare(right.repairKey),
        )[0] ?? null
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
