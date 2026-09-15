export const MANUAL_SELECTION_REPAIR_SCHEMA =
  'manual-image-selection-repair-v2' as const;
export const MANUAL_SELECTION_LEGACY_REPAIR_SCHEMA =
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

/** `restore` exists solely to finalize a v1 operation interrupted before migration. */
export type RepairOperationKind = 'fill' | 'undo_fill' | 'delete' | 'restore';
export type LegacyRepairOperationKind = RepairOperationKind;

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

export interface LegacyRepairOperation extends Omit<RepairOperation, 'kind'> {
  readonly kind: LegacyRepairOperationKind;
}

export interface PendingRepairOperation extends RepairOperation {
  readonly expectedFileState: 'absent' | 'present';
}

export interface DeletedRepairSource extends SequenceRange {
  readonly fileName: string;
  readonly checksumSha256: string;
  readonly sourcePath: string | null;
  readonly sourceIndex: number | null;
}

export interface ManualSelectionFilledGapEntry extends SequenceRange {
  readonly fileName: string;
  readonly checksumSha256: string;
  readonly sourcePath: string;
  readonly sourceIndex: number | null;
  readonly fillOperationId: string;
  readonly filledAt: string;
}

/** Current compact state. It deliberately has no append-only interaction log. */
export interface ManualSelectionRepairManifest {
  readonly schemaVersion: typeof MANUAL_SELECTION_REPAIR_SCHEMA;
  readonly repairKey: string;
  readonly selectedDirectoryName: string;
  readonly collectionStart: number;
  readonly collectionEnd: number;
  readonly revision: number;
  readonly activeFiles: readonly RepairActiveFile[];
  readonly deletedRanges: readonly SequenceRange[];
  readonly deletedSources: readonly DeletedRepairSource[];
  readonly filledGapEntries: readonly ManualSelectionFilledGapEntry[];
  readonly pendingOperation: PendingRepairOperation | null;
  readonly updatedAt: string;
}

export interface LegacyManualSelectionRepairManifest {
  readonly schemaVersion: typeof MANUAL_SELECTION_LEGACY_REPAIR_SCHEMA;
  readonly repairKey: string;
  readonly selectedDirectoryName: string;
  readonly collectionStart: number;
  readonly collectionEnd: number;
  readonly revision: number;
  readonly activeFiles: readonly RepairActiveFile[];
  readonly deletedRanges: readonly SequenceRange[];
  readonly operations: readonly LegacyRepairOperation[];
  readonly pendingOperation:
    | (LegacyRepairOperation & {
        readonly expectedFileState: 'absent' | 'present';
      })
    | null;
  readonly updatedAt: string;
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
  if (match === null) throw new Error(`INVALID_SEQUENCE_FILE_NAME:${fileName}`);
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
  readonly repairManifest:
    ManualSelectionRepairManifest | LegacyManualSelectionRepairManifest | null;
  readonly outputBounds: SequenceRange | null;
  readonly files: readonly ParsedSequenceFile[];
}): SequenceRange {
  const evidence: SequenceRange[] = [...input.files];
  if (input.outputBounds !== null) evidence.push(input.outputBounds);
  if (input.repairManifest !== null) {
    evidence.push(
      {
        end: input.repairManifest.collectionEnd,
        start: input.repairManifest.collectionStart,
      },
      ...input.repairManifest.activeFiles,
      ...input.repairManifest.deletedRanges,
    );
    if ('operations' in input.repairManifest) {
      evidence.push(
        ...input.repairManifest.operations.map((operation) => ({
          end: operation.rangeEnd,
          start: operation.rangeStart,
        })),
      );
    } else {
      evidence.push(...input.repairManifest.deletedSources);
    }
    if (input.repairManifest.pendingOperation !== null) {
      evidence.push({
        end: input.repairManifest.pendingOperation.rangeEnd,
        start: input.repairManifest.pendingOperation.rangeStart,
      });
    }
  }
  if (evidence.length === 0) throw new Error('SEQUENCE_COLLECTION_EMPTY');
  let start = evidence[0]!.start;
  let end = evidence[0]!.end;
  for (const range of evidence.slice(1)) {
    start = Math.min(start, range.start);
    end = Math.max(end, range.end);
  }
  return { end, start };
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
    deletedSources: [],
    filledGapEntries: [],
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
  validateManifestBase(manifest);
  if (
    !Array.isArray(manifest.deletedSources) ||
    !Array.isArray(manifest.filledGapEntries)
  ) {
    throw new Error('INVALID_REPAIR_MANIFEST');
  }
  validateActiveFiles(manifest.activeFiles);
  validateRanges(manifest.deletedRanges);
  validateDeletedSources(manifest.deletedSources);
  validateFilledEntries(manifest.filledGapEntries);
  validatePendingOperation(manifest.pendingOperation);
  return manifest;
}

export function validateLegacyRepairManifest(
  value: unknown,
): LegacyManualSelectionRepairManifest {
  if (
    !isObject(value) ||
    value.schemaVersion !== MANUAL_SELECTION_LEGACY_REPAIR_SCHEMA
  ) {
    throw new Error('INVALID_REPAIR_MANIFEST');
  }
  const manifest = value as unknown as LegacyManualSelectionRepairManifest;
  validateManifestBase(manifest);
  if (!Array.isArray(manifest.operations))
    throw new Error('INVALID_REPAIR_MANIFEST');
  validateActiveFiles(manifest.activeFiles);
  validateRanges(manifest.deletedRanges);
  for (const operation of manifest.operations)
    validateLegacyOperation(operation, false);
  if (manifest.pendingOperation !== null)
    validateLegacyOperation(manifest.pendingOperation, true);
  return manifest;
}

export function migrateLegacyRepairManifest(
  legacy: LegacyManualSelectionRepairManifest,
): ManualSelectionRepairManifest {
  validateLegacyRepairManifest(legacy);
  const activeByName = new Map(
    legacy.activeFiles.map((file) => [file.fileName, file]),
  );
  const filledByName = new Map<string, ManualSelectionFilledGapEntry>();
  const deletedByName = new Map<string, DeletedRepairSource>();
  for (const operation of legacy.operations) {
    if (operation.kind === 'fill' && operation.sourcePath !== null) {
      filledByName.set(operation.fileName, filledEntryFromOperation(operation));
    } else if (operation.kind === 'undo_fill') {
      filledByName.delete(operation.fileName);
    } else if (operation.kind === 'delete') {
      deletedByName.set(
        operation.fileName,
        deletedSourceFromOperation(operation),
      );
    } else if (operation.kind === 'restore') {
      deletedByName.delete(operation.fileName);
    }
  }
  for (const fileName of activeByName.keys()) deletedByName.delete(fileName);
  const compactPending = legacy.pendingOperation;
  return {
    activeFiles: legacy.activeFiles,
    collectionEnd: legacy.collectionEnd,
    collectionStart: legacy.collectionStart,
    deletedRanges: legacy.deletedRanges,
    deletedSources: [...deletedByName.values()].sort(compareFileRange),
    filledGapEntries: [...filledByName.values()]
      .filter((entry) => {
        const active = activeByName.get(entry.fileName);
        return active?.checksumSha256 === entry.checksumSha256;
      })
      .sort(compareFileRange),
    pendingOperation: compactPending,
    repairKey: legacy.repairKey,
    revision: legacy.revision,
    schemaVersion: MANUAL_SELECTION_REPAIR_SCHEMA,
    selectedDirectoryName: legacy.selectedDirectoryName,
    updatedAt: legacy.updatedAt,
  };
}

export function deriveFilledGapsManifest(
  manifest: ManualSelectionRepairManifest,
): ManualSelectionFilledGapsManifest {
  validateRepairManifest(manifest);
  const activeByName = new Map(
    manifest.activeFiles.map((file) => [file.fileName, file]),
  );
  const entries = manifest.filledGapEntries
    .filter((entry) => {
      const active = activeByName.get(entry.fileName);
      return active?.checksumSha256 === entry.checksumSha256;
    })
    .sort(compareFileRange);
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
  validateFilledEntries(manifest.entries);
  return manifest;
}

export function finalizePendingRepairOperation(
  manifest: ManualSelectionRepairManifest,
  actualState: 'absent' | 'present',
  now: string,
): ManualSelectionRepairManifest {
  validateRepairManifest(manifest);
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
  const filledGapEntries = manifest.filledGapEntries.filter(
    (entry) => entry.fileName !== pending.fileName,
  );
  if (pending.kind === 'fill') {
    if (pending.sourcePath === null)
      throw new Error('REPAIR_FILL_SOURCE_PATH_REQUIRED');
    filledGapEntries.push(filledEntryFromOperation(pending));
  }
  const deletedSources = manifest.deletedSources.filter(
    (entry) => entry.fileName !== pending.fileName,
  );
  if (pending.kind === 'delete')
    deletedSources.push(deletedSourceFromOperation(pending));
  return {
    ...manifest,
    activeFiles: [...activeFiles].sort(compareFileRange),
    deletedRanges: [...deletedRanges].sort(compareRange),
    deletedSources: [...deletedSources].sort(compareFileRange),
    filledGapEntries: [...filledGapEntries].sort(compareFileRange),
    pendingOperation: null,
    revision: manifest.revision + 1,
    updatedAt: now,
  };
}

function filledEntryFromOperation(
  operation: Pick<
    RepairOperation,
    | 'checksumSha256'
    | 'fileName'
    | 'id'
    | 'occurredAt'
    | 'rangeEnd'
    | 'rangeStart'
    | 'sourceIndex'
    | 'sourcePath'
  >,
): ManualSelectionFilledGapEntry {
  if (operation.sourcePath === null)
    throw new Error('REPAIR_FILL_SOURCE_PATH_REQUIRED');
  return {
    checksumSha256: operation.checksumSha256,
    end: operation.rangeEnd,
    fileName: operation.fileName,
    fillOperationId: operation.id,
    filledAt: operation.occurredAt,
    sourceIndex: operation.sourceIndex,
    sourcePath: operation.sourcePath,
    start: operation.rangeStart,
  };
}

function deletedSourceFromOperation(
  operation: Pick<
    RepairOperation,
    | 'checksumSha256'
    | 'fileName'
    | 'rangeEnd'
    | 'rangeStart'
    | 'sourceIndex'
    | 'sourcePath'
  >,
): DeletedRepairSource {
  return {
    checksumSha256: operation.checksumSha256,
    end: operation.rangeEnd,
    fileName: operation.fileName,
    sourceIndex: operation.sourceIndex,
    sourcePath: operation.sourcePath,
    start: operation.rangeStart,
  };
}

function validateManifestBase(
  manifest: ManualSelectionRepairManifest | LegacyManualSelectionRepairManifest,
): void {
  if (
    typeof manifest.repairKey !== 'string' ||
    manifest.repairKey.length < 1 ||
    typeof manifest.selectedDirectoryName !== 'string' ||
    !Number.isSafeInteger(manifest.revision) ||
    manifest.revision < 0 ||
    !Array.isArray(manifest.activeFiles) ||
    !Array.isArray(manifest.deletedRanges) ||
    typeof manifest.updatedAt !== 'string'
  ) {
    throw new Error('INVALID_REPAIR_MANIFEST');
  }
  validateBounds({
    end: manifest.collectionEnd,
    start: manifest.collectionStart,
  });
}

function validateActiveFiles(files: readonly RepairActiveFile[]): void {
  sortAndValidateSequenceFiles(files.map((file) => file.fileName));
  for (const file of files) {
    const parsed = parseSequenceFileName(file.fileName);
    if (parsed.start !== file.start || parsed.end !== file.end)
      throw new Error('INVALID_REPAIR_MANIFEST_FILE_RANGE');
    if (
      file.checksumSha256 !== null &&
      !/^[0-9a-f]{64}$/u.test(file.checksumSha256)
    ) {
      throw new Error('INVALID_REPAIR_MANIFEST_CHECKSUM');
    }
  }
}

function validateRanges(ranges: readonly SequenceRange[]): void {
  for (const range of ranges) validateSequenceRange(range);
}

function validateDeletedSources(entries: readonly DeletedRepairSource[]): void {
  sortAndValidateSequenceFiles(entries.map((entry) => entry.fileName));
  for (const entry of entries) {
    validateNamedEntry(entry);
    if (
      entry.sourcePath !== null &&
      (typeof entry.sourcePath !== 'string' || entry.sourcePath.length < 1)
    ) {
      throw new Error('INVALID_REPAIR_DELETED_SOURCE');
    }
    validateSourceIndex(entry.sourceIndex);
  }
}

function validateFilledEntries(
  entries: readonly ManualSelectionFilledGapEntry[],
): void {
  sortAndValidateSequenceFiles(entries.map((entry) => entry.fileName));
  for (const entry of entries) {
    validateNamedEntry(entry);
    if (
      entry.sourcePath.length < 1 ||
      entry.fillOperationId.length < 1 ||
      typeof entry.filledAt !== 'string'
    ) {
      throw new Error('INVALID_FILLED_GAPS_MANIFEST_ENTRY');
    }
    validateSourceIndex(entry.sourceIndex);
  }
}

function validatePendingOperation(
  pending: PendingRepairOperation | null,
): void {
  if (pending === null) return;
  validateRepairOperation(pending, true);
}

function validateLegacyOperation(
  operation:
    | LegacyRepairOperation
    | (LegacyRepairOperation & {
        readonly expectedFileState: 'absent' | 'present';
      }),
  pending: boolean,
): void {
  if (!['fill', 'undo_fill', 'delete', 'restore'].includes(operation.kind))
    throw new Error('INVALID_REPAIR_MANIFEST_OPERATION');
  validateOperationFields(operation, pending);
}

function validateRepairOperation(
  operation: PendingRepairOperation,
  pending: boolean,
): void {
  if (!['fill', 'undo_fill', 'delete', 'restore'].includes(operation.kind))
    throw new Error('INVALID_REPAIR_MANIFEST_OPERATION');
  validateOperationFields(operation, pending);
}

function validateOperationFields(
  operation: Pick<
    RepairOperation,
    | 'checksumSha256'
    | 'fileName'
    | 'id'
    | 'occurredAt'
    | 'rangeEnd'
    | 'rangeStart'
    | 'sourceIndex'
    | 'sourcePath'
  > & { readonly expectedFileState?: unknown },
  pending: boolean,
): void {
  const parsed = parseSequenceFileName(operation.fileName);
  if (
    parsed.start !== operation.rangeStart ||
    parsed.end !== operation.rangeEnd ||
    operation.id.length < 1 ||
    typeof operation.occurredAt !== 'string' ||
    !/^[0-9a-f]{64}$/u.test(operation.checksumSha256) ||
    (operation.sourcePath !== null &&
      (typeof operation.sourcePath !== 'string' ||
        operation.sourcePath.length < 1)) ||
    (pending &&
      operation.expectedFileState !== 'absent' &&
      operation.expectedFileState !== 'present')
  ) {
    throw new Error('INVALID_REPAIR_MANIFEST_OPERATION');
  }
  validateSourceIndex(operation.sourceIndex);
}

function validateNamedEntry(
  entry: Pick<
    DeletedRepairSource,
    'checksumSha256' | 'end' | 'fileName' | 'start'
  >,
): void {
  const parsed = parseSequenceFileName(entry.fileName);
  if (
    parsed.start !== entry.start ||
    parsed.end !== entry.end ||
    !/^[0-9a-f]{64}$/u.test(entry.checksumSha256)
  ) {
    throw new Error('INVALID_REPAIR_MANIFEST_ENTRY');
  }
}

function validateSourceIndex(value: number | null): void {
  if (value !== null && (!Number.isSafeInteger(value) || value < 0))
    throw new Error('INVALID_REPAIR_MANIFEST_SOURCE_INDEX');
}

function validateSequenceRange(range: SequenceRange): void {
  validateBounds(range);
  if (range.end - range.start + 1 > 9)
    throw new Error('INVALID_REPAIR_MANIFEST_RANGE');
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
    .sort(compareRange);
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

function compareRange(left: SequenceRange, right: SequenceRange): number {
  return left.start - right.start || left.end - right.end;
}

function compareFileRange(
  left: Pick<RepairActiveFile, 'end' | 'fileName' | 'start'>,
  right: Pick<RepairActiveFile, 'end' | 'fileName' | 'start'>,
): number {
  return (
    compareRange(left, right) || left.fileName.localeCompare(right.fileName)
  );
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
