export const MANUAL_SELECTION_REPAIR_SCHEMA =
  'manual-image-selection-repair-v1' as const;
export const MANUAL_SELECTION_FILLED_GAPS_SCHEMA =
  'manual-image-selection-filled-gaps-v1' as const;

export interface SequenceRange {
  readonly start: number;
  readonly end: number;
}

export interface RepairActiveFile extends SequenceRange {
  readonly fileName: string;
  readonly checksumSha256: string | null;
}

export type RepairOperationKind = 'fill' | 'undo_fill' | 'delete' | 'restore';

export interface RepairOperation {
  readonly id: string;
  readonly kind: RepairOperationKind;
  readonly fileName: string;
  readonly rangeStart: number;
  readonly rangeEnd: number;
  readonly checksumSha256: string;
  readonly sourcePath: string | null;
  readonly sourceIndex: number | null;
  readonly occurredAt: string;
}

export interface PendingRepairOperation extends RepairOperation {
  readonly expectedFileState: 'absent' | 'present';
}

export interface ManualSelectionRepairManifest {
  readonly schemaVersion: typeof MANUAL_SELECTION_REPAIR_SCHEMA;
  readonly repairKey: string;
  readonly selectedDirectoryName: string;
  readonly collectionStart: number;
  readonly collectionEnd: number;
  readonly revision: number;
  readonly activeFiles: readonly RepairActiveFile[];
  readonly deletedRanges: readonly SequenceRange[];
  readonly operations: readonly RepairOperation[];
  readonly pendingOperation: PendingRepairOperation | null;
  readonly updatedAt: string;
}

export interface ManualSelectionFilledGapEntry extends SequenceRange {
  readonly fileName: string;
  readonly checksumSha256: string;
  readonly sourcePath: string;
  readonly sourceIndex: number | null;
  readonly fillOperationId: string;
  readonly filledAt: string;
}

export interface ManualSelectionFilledGapsManifest {
  readonly schemaVersion: typeof MANUAL_SELECTION_FILLED_GAPS_SCHEMA;
  readonly repairKey: string;
  readonly selectedDirectoryName: string;
  readonly repairRevision: number;
  readonly entries: readonly ManualSelectionFilledGapEntry[];
  readonly updatedAt: string;
}

export interface ParsedSequenceFile extends SequenceRange {
  readonly fileName: string;
}

const SEQUENCE_FILE = /^seq_(\d+)-(\d+)\.(?:jpe?g)$/i;

export function parseSequenceFileName(fileName: string): ParsedSequenceFile {
  const match = SEQUENCE_FILE.exec(fileName);
  if (match === null) {
    throw new Error(`INVALID_SEQUENCE_FILE_NAME:${fileName}`);
  }
  const start = Number(match[1]);
  const end = Number(match[2]);
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 1 ||
    end < start ||
    end - start + 1 > 9
  ) {
    throw new Error(`INVALID_SEQUENCE_RANGE:${fileName}`);
  }
  return { end, fileName, start };
}

export function sortAndValidateSequenceFiles(
  fileNames: readonly string[],
): readonly ParsedSequenceFile[] {
  const parsed = fileNames
    .map(parseSequenceFileName)
    .sort(
      (left, right) =>
        left.start - right.start ||
        left.end - right.end ||
        left.fileName.localeCompare(right.fileName),
    );
  const names = new Set<string>();
  for (let index = 0; index < parsed.length; index += 1) {
    const current = parsed[index]!;
    const normalizedName = current.fileName.toLocaleLowerCase('en-US');
    if (names.has(normalizedName))
      throw new Error(`DUPLICATE_SEQUENCE_FILE:${current.fileName}`);
    names.add(normalizedName);
    const previous = parsed[index - 1];
    if (previous !== undefined && current.start <= previous.end) {
      throw new Error(
        `OVERLAPPING_SEQUENCE_RANGES:${previous.fileName}:${current.fileName}`,
      );
    }
  }
  return parsed;
}

export function deriveCollectionBounds(input: {
  readonly repairManifest: ManualSelectionRepairManifest | null;
  readonly outputBounds: SequenceRange | null;
  readonly files: readonly ParsedSequenceFile[];
}): SequenceRange {
  if (input.repairManifest !== null) {
    return {
      end: input.repairManifest.collectionEnd,
      start: input.repairManifest.collectionStart,
    };
  }
  if (input.outputBounds !== null) return input.outputBounds;
  if (input.files.length === 0) throw new Error('SEQUENCE_COLLECTION_EMPTY');
  return {
    end: input.files[input.files.length - 1]!.end,
    start: input.files[0]!.start,
  };
}

export function findSequenceGaps(
  bounds: SequenceRange,
  files: readonly ParsedSequenceFile[],
  deletedRanges: readonly SequenceRange[] = [],
): readonly SequenceRange[] {
  validateBounds(bounds);
  const knownDeletes = new Map(
    deletedRanges.map((range) => [`${range.start}:${range.end}`, range]),
  );
  const gaps: SequenceRange[] = [];
  let cursor = bounds.start;
  for (const file of files) {
    if (file.end < bounds.start || file.start > bounds.end) continue;
    if (file.start > cursor) {
      gaps.push(
        ...splitGap(
          { start: cursor, end: Math.min(file.start - 1, bounds.end) },
          knownDeletes,
        ),
      );
    }
    cursor = Math.max(cursor, file.end + 1);
    if (cursor > bounds.end) break;
  }
  if (cursor <= bounds.end) {
    gaps.push(...splitGap({ start: cursor, end: bounds.end }, knownDeletes));
  }
  return gaps;
}

export function createRepairManifest(input: {
  readonly repairKey: string;
  readonly selectedDirectoryName: string;
  readonly bounds: SequenceRange;
  readonly files: readonly ParsedSequenceFile[];
  readonly now: string;
}): ManualSelectionRepairManifest {
  validateBounds(input.bounds);
  return {
    activeFiles: input.files.map((file) => ({
      ...file,
      checksumSha256: null,
    })),
    collectionEnd: input.bounds.end,
    collectionStart: input.bounds.start,
    deletedRanges: [],
    operations: [],
    pendingOperation: null,
    repairKey: input.repairKey,
    revision: 0,
    schemaVersion: MANUAL_SELECTION_REPAIR_SCHEMA,
    selectedDirectoryName: input.selectedDirectoryName,
    updatedAt: input.now,
  };
}

export function validateRepairManifest(
  value: unknown,
): ManualSelectionRepairManifest {
  if (
    !isObject(value) ||
    value.schemaVersion !== MANUAL_SELECTION_REPAIR_SCHEMA
  )
    throw new Error('INVALID_REPAIR_MANIFEST');
  const manifest = value as unknown as ManualSelectionRepairManifest;
  if (
    typeof manifest.repairKey !== 'string' ||
    manifest.repairKey.length < 1 ||
    typeof manifest.selectedDirectoryName !== 'string' ||
    !Number.isSafeInteger(manifest.revision) ||
    manifest.revision < 0 ||
    !Array.isArray(manifest.activeFiles) ||
    !Array.isArray(manifest.deletedRanges) ||
    !Array.isArray(manifest.operations) ||
    typeof manifest.updatedAt !== 'string'
  ) {
    throw new Error('INVALID_REPAIR_MANIFEST');
  }
  validateBounds({
    end: manifest.collectionEnd,
    start: manifest.collectionStart,
  });
  sortAndValidateSequenceFiles(
    manifest.activeFiles.map((file) => file.fileName),
  );
  for (const file of manifest.activeFiles) {
    const parsed = parseSequenceFileName(file.fileName);
    if (parsed.start !== file.start || parsed.end !== file.end)
      throw new Error('INVALID_REPAIR_MANIFEST_FILE_RANGE');
    if (
      file.checksumSha256 !== null &&
      !/^[0-9a-f]{64}$/u.test(file.checksumSha256)
    )
      throw new Error('INVALID_REPAIR_MANIFEST_CHECKSUM');
  }
  return manifest;
}

export function deriveFilledGapsManifest(
  manifest: ManualSelectionRepairManifest,
): ManualSelectionFilledGapsManifest {
  validateRepairManifest(manifest);
  const activeByName = new Map(
    manifest.activeFiles.map((file) => [file.fileName, file]),
  );
  const latestFillByName = new Map<string, RepairOperation>();
  const undoneFillNames = new Set<string>();
  for (const operation of manifest.operations) {
    if (operation.kind === 'fill') {
      latestFillByName.set(operation.fileName, operation);
      undoneFillNames.delete(operation.fileName);
    } else if (operation.kind === 'undo_fill') {
      undoneFillNames.add(operation.fileName);
    }
  }
  const entries = [...latestFillByName.values()]
    .flatMap((operation) => {
      const active = activeByName.get(operation.fileName);
      if (
        active === undefined ||
        undoneFillNames.has(operation.fileName) ||
        active.checksumSha256 !== operation.checksumSha256 ||
        operation.sourcePath === null
      )
        return [];
      return [
        {
          checksumSha256: operation.checksumSha256,
          end: operation.rangeEnd,
          fileName: operation.fileName,
          fillOperationId: operation.id,
          filledAt: operation.occurredAt,
          sourceIndex: operation.sourceIndex,
          sourcePath: operation.sourcePath,
          start: operation.rangeStart,
        },
      ];
    })
    .sort((left, right) => left.start - right.start || left.end - right.end);
  return {
    entries,
    repairKey: manifest.repairKey,
    repairRevision: manifest.revision,
    schemaVersion: MANUAL_SELECTION_FILLED_GAPS_SCHEMA,
    selectedDirectoryName: manifest.selectedDirectoryName,
    updatedAt: manifest.updatedAt,
  };
}

export function validateFilledGapsManifest(
  value: unknown,
): ManualSelectionFilledGapsManifest {
  if (
    !isObject(value) ||
    value.schemaVersion !== MANUAL_SELECTION_FILLED_GAPS_SCHEMA ||
    typeof value.repairKey !== 'string' ||
    value.repairKey.length < 1 ||
    typeof value.selectedDirectoryName !== 'string' ||
    !Number.isSafeInteger(value.repairRevision) ||
    (value.repairRevision as number) < 0 ||
    !Array.isArray(value.entries) ||
    typeof value.updatedAt !== 'string'
  )
    throw new Error('INVALID_FILLED_GAPS_MANIFEST');
  const manifest = value as unknown as ManualSelectionFilledGapsManifest;
  sortAndValidateSequenceFiles(manifest.entries.map((entry) => entry.fileName));
  for (const entry of manifest.entries) {
    const parsed = parseSequenceFileName(entry.fileName);
    if (
      parsed.start !== entry.start ||
      parsed.end !== entry.end ||
      !/^[0-9a-f]{64}$/u.test(entry.checksumSha256) ||
      entry.sourcePath.length < 1 ||
      entry.fillOperationId.length < 1 ||
      typeof entry.filledAt !== 'string' ||
      (entry.sourceIndex !== null &&
        (!Number.isSafeInteger(entry.sourceIndex) || entry.sourceIndex < 0))
    )
      throw new Error('INVALID_FILLED_GAPS_MANIFEST_ENTRY');
  }
  return manifest;
}

export function finalizePendingRepairOperation(
  manifest: ManualSelectionRepairManifest,
  actualState: 'absent' | 'present',
  now: string,
): ManualSelectionRepairManifest {
  const pending = manifest.pendingOperation;
  if (pending === null) return manifest;
  if (pending.expectedFileState !== actualState)
    throw new Error('REPAIR_PENDING_OPERATION_NOT_APPLIED');
  const activeFiles = manifest.activeFiles.filter(
    (file) => file.fileName !== pending.fileName,
  );
  if (actualState === 'present') {
    activeFiles.push({
      checksumSha256: pending.checksumSha256,
      end: pending.rangeEnd,
      fileName: pending.fileName,
      start: pending.rangeStart,
    });
  }
  const deletedRanges = manifest.deletedRanges.filter(
    (range) =>
      range.start !== pending.rangeStart || range.end !== pending.rangeEnd,
  );
  if (pending.kind === 'delete' || pending.kind === 'undo_fill') {
    deletedRanges.push({ end: pending.rangeEnd, start: pending.rangeStart });
  }
  return {
    ...manifest,
    activeFiles: [...activeFiles].sort(
      (left, right) => left.start - right.start || left.end - right.end,
    ),
    deletedRanges: [...deletedRanges].sort(
      (left, right) => left.start - right.start || left.end - right.end,
    ),
    operations: manifest.operations.some(
      (operation) => operation.id === pending.id,
    )
      ? manifest.operations
      : [...manifest.operations, pending],
    pendingOperation: null,
    revision: manifest.revision + 1,
    updatedAt: now,
  };
}

function splitGap(
  gap: SequenceRange,
  knownDeletes: ReadonlyMap<string, SequenceRange>,
): SequenceRange[] {
  if (gap.end < gap.start) return [];
  const result: SequenceRange[] = [];
  let cursor = gap.start;
  const deletes = [...knownDeletes.values()]
    .filter((range) => range.start >= gap.start && range.end <= gap.end)
    .sort((left, right) => left.start - right.start || left.end - right.end);
  for (const deletion of deletes) {
    while (cursor < deletion.start) {
      const end = Math.min(cursor + 8, deletion.start - 1);
      result.push({ end, start: cursor });
      cursor = end + 1;
    }
    if (cursor <= deletion.end) {
      result.push(deletion);
      cursor = deletion.end + 1;
    }
  }
  while (cursor <= gap.end) {
    const end = Math.min(cursor + 8, gap.end);
    result.push({ end, start: cursor });
    cursor = end + 1;
  }
  return result;
}

function validateBounds(bounds: SequenceRange): void {
  if (
    !Number.isSafeInteger(bounds.start) ||
    !Number.isSafeInteger(bounds.end) ||
    bounds.start < 1 ||
    bounds.end < bounds.start
  )
    throw new Error('INVALID_SEQUENCE_COLLECTION_BOUNDS');
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
