export const SEMI_AUTOMATIC_SELECTION_OUTPUT_SCHEMA_VERSION = 1 as const;
export const SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_FILE =
  'semi-automatic-image-selection-output-v1.json' as const;

const SHA256 = /^[0-9a-f]{64}$/u;
const OUTPUT_FILE = /^seq_(\d+)-(\d+)\.jpg$/u;

export type SemiAutomaticLocalOutputStatus =
  'syncing_output' | 'review_mode' | 'completed';

export type SemiAutomaticLocalSelectionStatus =
  | 'AUTO_SELECTED'
  | 'MANUALLY_ADDED'
  | 'MANUALLY_REPLACED'
  | 'PREEXISTING_PROTECTED';

export interface SemiAutomaticLocalSourceIdentity {
  readonly relativePath: string;
  readonly sourceIndex: number;
  readonly sizeBytes: number;
  readonly checksumSha256: string;
}

export interface SemiAutomaticLocalSelection {
  readonly expectedIndex: number;
  readonly rangeStart: number;
  readonly rangeEnd: number;
  readonly outputName: string;
  readonly outputChecksumSha256: string;
  readonly source: SemiAutomaticLocalSourceIdentity;
  readonly status: SemiAutomaticLocalSelectionStatus;
  readonly serverRangeRevision: number;
  readonly acknowledged: boolean;
  readonly selectedAt: string;
}

export interface SemiAutomaticLocalConflict {
  readonly expectedIndex: number;
  readonly outputName: string;
  readonly expectedChecksumSha256: string;
  readonly actualChecksumSha256: string;
  readonly detectedAt: string;
  readonly reason: 'TARGET_CONTENT_CHANGED' | 'PENDING_TARGET_CHANGED';
}

export interface SemiAutomaticLocalHistoryEvent {
  readonly eventIndex: number;
  readonly expectedIndex: number;
  readonly kind:
    | 'output_written'
    | 'preexisting_protected'
    | 'output_acknowledged'
    | 'pending_reconciled'
    | 'conflict_detected';
  readonly occurredAt: string;
  readonly source: SemiAutomaticLocalSourceIdentity | null;
  readonly previousSource: SemiAutomaticLocalSourceIdentity | null;
}

export interface SemiAutomaticPendingOutputOperation {
  readonly operationId: string;
  readonly expectedIndex: number;
  readonly rangeStart: number;
  readonly rangeEnd: number;
  readonly outputName: string;
  readonly expectedRangeRevision: number;
  readonly selectionStatus: 'AUTO_SELECTED' | 'PREEXISTING_PROTECTED';
  readonly source: SemiAutomaticLocalSourceIdentity;
  readonly startedAt: string;
}

export interface SemiAutomaticSelectionOutputManifestV1 {
  readonly schemaVersion: typeof SEMI_AUTOMATIC_SELECTION_OUTPUT_SCHEMA_VERSION;
  readonly runId: string;
  readonly status: SemiAutomaticLocalOutputStatus;
  readonly sourceDirectoryName: string;
  readonly outputDirectoryName: string;
  readonly sourceFingerprint: string;
  readonly sourceManifestChecksumSha256: string;
  readonly firstSequenceNumber: number;
  readonly lastSequenceNumber: number;
  readonly direction: 'ascending' | 'descending';
  readonly rangeConvention: 'seq-inclusive-v1';
  readonly fullRangeSize: 9;
  readonly expectedRangesFingerprint: string;
  readonly recognizerFingerprint: string;
  readonly groupingPolicyFingerprint: string;
  readonly selectorPolicyFingerprint: string;
  readonly diagnosticsChecksumSha256: string | null;
  readonly syncCheckpoint: {
    readonly lastExpectedIndex: number | null;
    readonly synchronizedCount: number;
  };
  readonly selections: readonly SemiAutomaticLocalSelection[];
  readonly gaps: readonly number[];
  readonly conflicts: readonly SemiAutomaticLocalConflict[];
  readonly history: readonly SemiAutomaticLocalHistoryEvent[];
  readonly pendingOperation: SemiAutomaticPendingOutputOperation | null;
  readonly revision: number;
  readonly updatedAt: string;
}

export interface SemiAutomaticRunIdentity {
  readonly id: string;
  readonly firstSequenceNumber: number;
  readonly lastSequenceNumber: number;
  readonly direction: 'ascending' | 'descending';
  readonly rangeConvention: 'seq-inclusive-v1';
  readonly fullRangeSize: 9;
  readonly expectedRangesFingerprint: string;
  readonly recognizerFingerprint: string;
  readonly groupingPolicyFingerprint: string;
  readonly diagnosticsChecksumSha256: string | null;
  readonly source: {
    readonly displayName: string;
    readonly sourceFingerprint: string;
    readonly manifestChecksumSha256: string;
  };
}

export function createSemiAutomaticSelectionOutputManifest(input: {
  readonly run: SemiAutomaticRunIdentity;
  readonly outputDirectoryName: string;
  readonly now: string;
}): SemiAutomaticSelectionOutputManifestV1 {
  validateRunIdentity(input.run);
  requireText(input.outputDirectoryName, 'output directory name');
  requireTimestamp(input.now);
  return {
    conflicts: [],
    diagnosticsChecksumSha256: input.run.diagnosticsChecksumSha256,
    direction: input.run.direction,
    expectedRangesFingerprint: input.run.expectedRangesFingerprint,
    firstSequenceNumber: input.run.firstSequenceNumber,
    fullRangeSize: input.run.fullRangeSize,
    gaps: [],
    groupingPolicyFingerprint: input.run.groupingPolicyFingerprint,
    history: [],
    lastSequenceNumber: input.run.lastSequenceNumber,
    outputDirectoryName: input.outputDirectoryName,
    pendingOperation: null,
    rangeConvention: input.run.rangeConvention,
    recognizerFingerprint: input.run.recognizerFingerprint,
    revision: 0,
    runId: input.run.id,
    schemaVersion: SEMI_AUTOMATIC_SELECTION_OUTPUT_SCHEMA_VERSION,
    selections: [],
    selectorPolicyFingerprint: input.run.groupingPolicyFingerprint,
    sourceDirectoryName: input.run.source.displayName,
    sourceFingerprint: input.run.source.sourceFingerprint,
    sourceManifestChecksumSha256: input.run.source.manifestChecksumSha256,
    status: 'syncing_output',
    syncCheckpoint: { lastExpectedIndex: null, synchronizedCount: 0 },
    updatedAt: input.now,
  };
}

export function parseSemiAutomaticSelectionOutputManifest(
  source: string,
): SemiAutomaticSelectionOutputManifestV1 {
  return validateSemiAutomaticSelectionOutputManifest(JSON.parse(source));
}

export function validateSemiAutomaticSelectionOutputManifest(
  value: unknown,
): SemiAutomaticSelectionOutputManifestV1 {
  if (!isObject(value) || value.schemaVersion !== 1) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_INVALID');
  }
  const manifest = value as unknown as SemiAutomaticSelectionOutputManifestV1;
  validateManifestHeader(manifest);
  if (
    !Array.isArray(manifest.selections) ||
    !Array.isArray(manifest.gaps) ||
    !Array.isArray(manifest.conflicts) ||
    !Array.isArray(manifest.history) ||
    !isObject(manifest.syncCheckpoint) ||
    !Number.isSafeInteger(manifest.syncCheckpoint.synchronizedCount) ||
    manifest.syncCheckpoint.synchronizedCount < 0 ||
    (manifest.syncCheckpoint.lastExpectedIndex !== null &&
      (!Number.isSafeInteger(manifest.syncCheckpoint.lastExpectedIndex) ||
        manifest.syncCheckpoint.lastExpectedIndex < 0)) ||
    !Number.isSafeInteger(manifest.revision) ||
    manifest.revision < 0
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_INVALID');
  }
  const expectedIndexes = new Set<number>();
  for (const selection of manifest.selections) {
    validateSelection(selection);
    if (expectedIndexes.has(selection.expectedIndex)) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SELECTION_DUPLICATE');
    }
    expectedIndexes.add(selection.expectedIndex);
  }
  for (const expectedIndex of manifest.gaps) requireIndex(expectedIndex);
  for (const conflict of manifest.conflicts) validateConflict(conflict);
  for (let index = 0; index < manifest.history.length; index += 1) {
    const event = manifest.history[index];
    if (!isObject(event) || event.eventIndex !== index) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_HISTORY_INVALID');
    }
    if (
      typeof event.expectedIndex !== 'number' ||
      typeof event.occurredAt !== 'string' ||
      typeof event.kind !== 'string' ||
      ![
        'output_written',
        'preexisting_protected',
        'output_acknowledged',
        'pending_reconciled',
        'conflict_detected',
      ].includes(event.kind) ||
      !('source' in event) ||
      !('previousSource' in event)
    ) {
      throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_HISTORY_INVALID');
    }
    requireIndex(event.expectedIndex);
    requireTimestamp(event.occurredAt);
    if (event.source !== null) validateSource(event.source);
    if (event.previousSource !== null) validateSource(event.previousSource);
  }
  if (manifest.pendingOperation !== null) {
    validatePendingOperation(manifest.pendingOperation);
  }
  return normalizeManifest(manifest);
}

export function assertSemiAutomaticManifestMatchesRun(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  run: SemiAutomaticRunIdentity,
  outputDirectoryName: string,
): void {
  validateRunIdentity(run);
  const matches =
    manifest.runId === run.id &&
    manifest.sourceDirectoryName === run.source.displayName &&
    manifest.outputDirectoryName === outputDirectoryName &&
    manifest.sourceFingerprint === run.source.sourceFingerprint &&
    manifest.sourceManifestChecksumSha256 ===
      run.source.manifestChecksumSha256 &&
    manifest.firstSequenceNumber === run.firstSequenceNumber &&
    manifest.lastSequenceNumber === run.lastSequenceNumber &&
    manifest.direction === run.direction &&
    manifest.rangeConvention === run.rangeConvention &&
    manifest.fullRangeSize === run.fullRangeSize &&
    manifest.expectedRangesFingerprint === run.expectedRangesFingerprint &&
    manifest.recognizerFingerprint === run.recognizerFingerprint &&
    manifest.groupingPolicyFingerprint === run.groupingPolicyFingerprint &&
    manifest.selectorPolicyFingerprint === run.groupingPolicyFingerprint;
  if (!matches) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_FOREIGN');
  }
}

export function serializeSemiAutomaticSelectionOutputManifest(
  manifest: SemiAutomaticSelectionOutputManifestV1,
): string {
  return `${JSON.stringify(validateSemiAutomaticSelectionOutputManifest(manifest), null, 2)}\n`;
}

export function beginSemiAutomaticOutputOperation(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  operation: SemiAutomaticPendingOutputOperation,
  now: string,
): SemiAutomaticSelectionOutputManifestV1 {
  if (manifest.pendingOperation !== null) {
    if (samePendingOperation(manifest.pendingOperation, operation))
      return manifest;
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_OPERATION_PENDING');
  }
  validatePendingOperation(operation);
  return bumpManifest(manifest, { pendingOperation: operation }, now);
}

export function rollbackSemiAutomaticOutputOperation(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  now: string,
): SemiAutomaticSelectionOutputManifestV1 {
  if (manifest.pendingOperation === null) return manifest;
  return bumpManifest(manifest, { pendingOperation: null }, now);
}

export function finalizeSemiAutomaticOutputOperation(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  now: string,
): SemiAutomaticSelectionOutputManifestV1 {
  const pending = manifest.pendingOperation;
  if (pending === null) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_OPERATION_MISSING');
  }
  const selection: SemiAutomaticLocalSelection = {
    acknowledged: false,
    expectedIndex: pending.expectedIndex,
    outputChecksumSha256: pending.source.checksumSha256,
    outputName: pending.outputName,
    rangeEnd: pending.rangeEnd,
    rangeStart: pending.rangeStart,
    selectedAt: now,
    serverRangeRevision: pending.expectedRangeRevision,
    source: pending.source,
    status: pending.selectionStatus,
  };
  const selections = replaceSelection(manifest.selections, selection);
  return bumpManifest(
    manifest,
    {
      history: appendHistory(manifest, {
        expectedIndex: pending.expectedIndex,
        kind:
          pending.selectionStatus === 'AUTO_SELECTED'
            ? 'output_written'
            : 'preexisting_protected',
        occurredAt: now,
        previousSource:
          manifest.selections.find(
            (item) => item.expectedIndex === pending.expectedIndex,
          )?.source ?? null,
        source: pending.source,
      }),
      pendingOperation: null,
      selections,
      syncCheckpoint: {
        lastExpectedIndex: pending.expectedIndex,
        synchronizedCount: selections.length,
      },
    },
    now,
  );
}

export function acknowledgeSemiAutomaticLocalSelection(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  expectedIndex: number,
  serverRangeRevision: number,
  now: string,
): SemiAutomaticSelectionOutputManifestV1 {
  const current = manifest.selections.find(
    (selection) => selection.expectedIndex === expectedIndex,
  );
  if (current === undefined) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SELECTION_MISSING');
  }
  if (
    current.acknowledged &&
    current.serverRangeRevision === serverRangeRevision
  ) {
    return manifest;
  }
  const selections = replaceSelection(manifest.selections, {
    ...current,
    acknowledged: true,
    serverRangeRevision,
  });
  return bumpManifest(
    manifest,
    {
      history: appendHistory(manifest, {
        expectedIndex,
        kind: 'output_acknowledged',
        occurredAt: now,
        previousSource: null,
        source: current.source,
      }),
      selections,
    },
    now,
  );
}

export function recordSemiAutomaticOutputConflict(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  conflict: SemiAutomaticLocalConflict,
  now: string,
): SemiAutomaticSelectionOutputManifestV1 {
  validateConflict(conflict);
  const conflicts = [
    ...manifest.conflicts.filter(
      (item) => item.expectedIndex !== conflict.expectedIndex,
    ),
    conflict,
  ].sort((left, right) => left.expectedIndex - right.expectedIndex);
  return bumpManifest(
    manifest,
    {
      conflicts,
      history: appendHistory(manifest, {
        expectedIndex: conflict.expectedIndex,
        kind: 'conflict_detected',
        occurredAt: now,
        previousSource: null,
        source: manifest.pendingOperation?.source ?? null,
      }),
      pendingOperation: null,
    },
    now,
  );
}

export function updateSemiAutomaticOutputSummary(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  input: {
    readonly gaps: readonly number[];
    readonly status: SemiAutomaticLocalOutputStatus;
    readonly now: string;
  },
): SemiAutomaticSelectionOutputManifestV1 {
  const gaps = [...new Set(input.gaps)].sort((left, right) => left - right);
  for (const expectedIndex of gaps) requireIndex(expectedIndex);
  if (
    manifest.status === input.status &&
    manifest.gaps.length === gaps.length &&
    manifest.gaps.every((value, index) => value === gaps[index])
  ) {
    return manifest;
  }
  return bumpManifest(manifest, { gaps, status: input.status }, input.now);
}

export function outputFileName(rangeStart: number, rangeEnd: number): string {
  validateRange(rangeStart, rangeEnd);
  return `seq_${rangeStart}-${rangeEnd}.jpg`;
}

function normalizeManifest(
  manifest: SemiAutomaticSelectionOutputManifestV1,
): SemiAutomaticSelectionOutputManifestV1 {
  return {
    ...manifest,
    conflicts: [...manifest.conflicts].sort(
      (left, right) => left.expectedIndex - right.expectedIndex,
    ),
    gaps: [...new Set(manifest.gaps)].sort((left, right) => left - right),
    history: [...manifest.history],
    selections: [...manifest.selections].sort(
      (left, right) => left.expectedIndex - right.expectedIndex,
    ),
  };
}

function bumpManifest(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  changes: Partial<SemiAutomaticSelectionOutputManifestV1>,
  now: string,
): SemiAutomaticSelectionOutputManifestV1 {
  requireTimestamp(now);
  return validateSemiAutomaticSelectionOutputManifest({
    ...manifest,
    ...changes,
    revision: manifest.revision + 1,
    updatedAt: now,
  });
}

function appendHistory(
  manifest: SemiAutomaticSelectionOutputManifestV1,
  event: Omit<SemiAutomaticLocalHistoryEvent, 'eventIndex'>,
): readonly SemiAutomaticLocalHistoryEvent[] {
  return [
    ...manifest.history,
    { ...event, eventIndex: manifest.history.length },
  ];
}

function replaceSelection(
  selections: readonly SemiAutomaticLocalSelection[],
  next: SemiAutomaticLocalSelection,
): readonly SemiAutomaticLocalSelection[] {
  return [
    ...selections.filter((item) => item.expectedIndex !== next.expectedIndex),
    next,
  ].sort((left, right) => left.expectedIndex - right.expectedIndex);
}

function validateManifestHeader(
  manifest: SemiAutomaticSelectionOutputManifestV1,
): void {
  requireText(manifest.runId, 'run id');
  requireText(manifest.sourceDirectoryName, 'source directory name');
  requireText(manifest.outputDirectoryName, 'output directory name');
  requireSha(manifest.sourceFingerprint);
  requireSha(manifest.sourceManifestChecksumSha256);
  requireSha(manifest.expectedRangesFingerprint);
  requireSha(manifest.recognizerFingerprint);
  requireSha(manifest.groupingPolicyFingerprint);
  requireSha(manifest.selectorPolicyFingerprint);
  if (manifest.diagnosticsChecksumSha256 !== null) {
    requireSha(manifest.diagnosticsChecksumSha256);
  }
  validateRange(
    manifest.firstSequenceNumber,
    manifest.lastSequenceNumber,
    false,
  );
  if (
    !['ascending', 'descending'].includes(manifest.direction) ||
    manifest.rangeConvention !== 'seq-inclusive-v1' ||
    manifest.fullRangeSize !== 9 ||
    !['syncing_output', 'review_mode', 'completed'].includes(manifest.status)
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_INVALID');
  }
  requireTimestamp(manifest.updatedAt);
}

function validateRunIdentity(run: SemiAutomaticRunIdentity): void {
  validateManifestHeader({
    conflicts: [],
    diagnosticsChecksumSha256: run.diagnosticsChecksumSha256,
    direction: run.direction,
    expectedRangesFingerprint: run.expectedRangesFingerprint,
    firstSequenceNumber: run.firstSequenceNumber,
    fullRangeSize: run.fullRangeSize,
    gaps: [],
    groupingPolicyFingerprint: run.groupingPolicyFingerprint,
    history: [],
    lastSequenceNumber: run.lastSequenceNumber,
    outputDirectoryName: 'output',
    pendingOperation: null,
    rangeConvention: run.rangeConvention,
    recognizerFingerprint: run.recognizerFingerprint,
    revision: 0,
    runId: run.id,
    schemaVersion: 1,
    selections: [],
    selectorPolicyFingerprint: run.groupingPolicyFingerprint,
    sourceDirectoryName: run.source.displayName,
    sourceFingerprint: run.source.sourceFingerprint,
    sourceManifestChecksumSha256: run.source.manifestChecksumSha256,
    status: 'syncing_output',
    syncCheckpoint: { lastExpectedIndex: null, synchronizedCount: 0 },
    updatedAt: new Date(0).toISOString(),
  });
}

function validateSelection(selection: SemiAutomaticLocalSelection): void {
  if (!isObject(selection)) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SELECTION_INVALID');
  }
  requireIndex(selection.expectedIndex);
  validateRange(selection.rangeStart, selection.rangeEnd);
  if (
    selection.outputName !==
    outputFileName(selection.rangeStart, selection.rangeEnd)
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SELECTION_INVALID');
  }
  requireSha(selection.outputChecksumSha256);
  validateSource(selection.source);
  if (
    ![
      'AUTO_SELECTED',
      'MANUALLY_ADDED',
      'MANUALLY_REPLACED',
      'PREEXISTING_PROTECTED',
    ].includes(selection.status) ||
    !Number.isSafeInteger(selection.serverRangeRevision) ||
    selection.serverRangeRevision < 0 ||
    typeof selection.acknowledged !== 'boolean'
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SELECTION_INVALID');
  }
  requireTimestamp(selection.selectedAt);
}

function validatePendingOperation(
  operation: SemiAutomaticPendingOutputOperation,
): void {
  if (!isObject(operation)) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_OPERATION_INVALID');
  }
  requireText(operation.operationId, 'operation id');
  requireIndex(operation.expectedIndex);
  validateRange(operation.rangeStart, operation.rangeEnd);
  if (
    operation.outputName !==
    outputFileName(operation.rangeStart, operation.rangeEnd)
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_OPERATION_INVALID');
  }
  if (
    !['AUTO_SELECTED', 'PREEXISTING_PROTECTED'].includes(
      operation.selectionStatus,
    ) ||
    !Number.isSafeInteger(operation.expectedRangeRevision) ||
    operation.expectedRangeRevision < 0
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_OPERATION_INVALID');
  }
  validateSource(operation.source);
  requireTimestamp(operation.startedAt);
}

function validateConflict(conflict: SemiAutomaticLocalConflict): void {
  if (!isObject(conflict)) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_CONFLICT_INVALID');
  }
  requireIndex(conflict.expectedIndex);
  if (OUTPUT_FILE.exec(conflict.outputName) === null) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_CONFLICT_INVALID');
  }
  requireSha(conflict.expectedChecksumSha256);
  requireSha(conflict.actualChecksumSha256);
  requireTimestamp(conflict.detectedAt);
  if (
    conflict.reason !== 'TARGET_CONTENT_CHANGED' &&
    conflict.reason !== 'PENDING_TARGET_CHANGED'
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_CONFLICT_INVALID');
  }
}

function validateSource(
  source: unknown,
): asserts source is SemiAutomaticLocalSourceIdentity {
  if (!isObject(source)) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SOURCE_INVALID');
  }
  if (
    typeof source.relativePath !== 'string' ||
    typeof source.sourceIndex !== 'number' ||
    typeof source.sizeBytes !== 'number' ||
    typeof source.checksumSha256 !== 'string'
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SOURCE_INVALID');
  }
  requireText(source.relativePath, 'relative path');
  requireIndex(source.sourceIndex);
  if (!Number.isSafeInteger(source.sizeBytes) || source.sizeBytes < 1) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_SOURCE_INVALID');
  }
  requireSha(source.checksumSha256);
}

function validateRange(start: number, end: number, limit = true): void {
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 1 ||
    end < start ||
    (limit && end - start + 1 > 9)
  ) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_RANGE_INVALID');
  }
}

function requireIndex(value: number): void {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_INDEX_INVALID');
  }
}

function requireSha(value: string): void {
  if (!SHA256.test(value)) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_CHECKSUM_INVALID');
  }
}

function requireText(value: string, _name: string): void {
  void _name;
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_MANIFEST_INVALID');
  }
}

function requireTimestamp(value: string): void {
  if (typeof value !== 'string' || !Number.isFinite(Date.parse(value))) {
    throw new Error('SEMI_AUTOMATIC_SELECTION_OUTPUT_TIMESTAMP_INVALID');
  }
}

function samePendingOperation(
  left: SemiAutomaticPendingOutputOperation,
  right: SemiAutomaticPendingOutputOperation,
): boolean {
  return (
    left.operationId === right.operationId &&
    left.expectedIndex === right.expectedIndex &&
    left.outputName === right.outputName &&
    left.selectionStatus === right.selectionStatus &&
    left.source.checksumSha256 === right.source.checksumSha256
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
