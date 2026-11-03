import type {
  SourceReplacementRequestExport,
  SourceReplacementEntryResponse,
} from '@game-predictor/admin-api-client/types';
import {
  parseSequenceFileName,
  type ManualSelectionFilledGapsManifest,
  type ManualSelectionFilledGapEntry,
} from '@game-predictor/manual-image-selection-core/repair';

export const REPLACEMENT_REPAIR_SCHEMA =
  'manual-image-selection-repair-v3' as const;
export type ReplacementRequest = SourceReplacementRequestExport;
export interface ReplacementWrite {
  readonly id: string;
  readonly entryId: string;
  readonly fileName: string;
  readonly checksumSha256: string;
  readonly size: number;
  readonly sourcePath: string;
  readonly sourceIndex: number | null;
  readonly occurredAt: string;
  readonly state: 'intent' | 'committed';
}
export interface ReplacementRepairManifest {
  readonly schemaVersion: typeof REPLACEMENT_REPAIR_SCHEMA;
  readonly mode: 'source_replacement';
  readonly repairKey: string;
  readonly selectedDirectoryName: string;
  readonly request: ReplacementRequest;
  readonly revision: number;
  readonly journal: readonly ReplacementWrite[];
  readonly updatedAt: string;
}
const object = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const sha = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const uuid = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(v);
const positive = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const fail = (code: string): never => {
  throw new Error(code);
};

/** Request values are ASCII strings and safe integers; key order matches Python sort_keys. */
export function replacementCanonicalJson(value: unknown): string {
  if (Array.isArray(value))
    return `[${value.map(replacementCanonicalJson).join(',')}]`;
  if (object(value))
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}:${replacementCanonicalJson(value[key])}`,
      )
      .join(',')}}`;
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'boolean' ||
    (typeof value === 'number' && Number.isSafeInteger(value))
  )
    return JSON.stringify(value);
  return fail('REPLACEMENT_INVALID_JSON');
}

export function replacementRequestPayload(
  request: ReplacementRequest,
): Omit<ReplacementRequest, 'digest'> {
  return {
    schemaVersion: request.schemaVersion,
    gameId: request.gameId,
    batchId: request.batchId,
    entries: request.entries,
    allowedRanges: request.allowedRanges,
  };
}

/** Runtime validation consumes the generated API type, never a second wire model. */
export function parseReplacementRequest(value: unknown): ReplacementRequest {
  if (
    !object(value) ||
    value.schemaVersion !== 'source-replacement-request-v1' ||
    !uuid(value.gameId) ||
    !uuid(value.batchId) ||
    !sha(value.digest) ||
    !Array.isArray(value.entries) ||
    value.entries.length < 1 ||
    value.entries.length > 50 ||
    !Array.isArray(value.allowedRanges) ||
    value.allowedRanges.length !== value.entries.length
  )
    return fail('REPLACEMENT_INVALID_REQUEST');
  const request = value as unknown as ReplacementRequest;
  const ids = new Set<string>();
  const sequences = new Set<number>();
  for (const entry of request.entries) {
    if (
      !object(entry) ||
      !uuid(entry.entryId) ||
      ids.has(entry.entryId) ||
      !positive(entry.revision) ||
      !sha(entry.digest) ||
      !sha(entry.sourceSha256) ||
      !Array.isArray(entry.sequenceNumbers) ||
      entry.sequenceNumbers.length < 1 ||
      entry.sequenceNumbers.length > 9
    )
      return fail('REPLACEMENT_INVALID_ENTRY');
    ids.add(entry.entryId);
    const ranges = request.allowedRanges.filter(
      (range) => object(range) && range.entryId === entry.entryId,
    );
    const range = ranges[0];
    if (
      ranges.length !== 1 ||
      !range ||
      !positive(range.sequenceStart) ||
      !positive(range.sequenceEnd) ||
      range.sequenceEnd - range.sequenceStart + 1 !==
        entry.sequenceNumbers.length
    )
      return fail('REPLACEMENT_INVALID_RANGE');
    entry.sequenceNumbers.forEach((seq, index) => {
      if (
        !positive(seq) ||
        seq !== range.sequenceStart + index ||
        sequences.has(seq)
      )
        fail('REPLACEMENT_INVALID_SEQUENCE_SCOPE');
      sequences.add(seq);
    });
  }
  // Return only known fields. Informational file metadata cannot select an API server.
  return replacementRequestPayloadWithDigest(request);
}

function replacementRequestPayloadWithDigest(
  request: ReplacementRequest,
): ReplacementRequest {
  return { ...replacementRequestPayload(request), digest: request.digest };
}

export function replacementRange(request: ReplacementRequest, entryId: string) {
  return (
    request.allowedRanges.find((range) => range.entryId === entryId) ??
    fail('REPLACEMENT_ENTRY_NOT_SELECTED')
  );
}

export function validateReplacementTarget(
  request: ReplacementRequest,
  entryId: string,
  fileName: string,
): void {
  const range = replacementRange(request, entryId);
  const parsed = parseSequenceFileName(fileName);
  if (parsed.start !== range.sequenceStart || parsed.end !== range.sequenceEnd)
    fail('REPLACEMENT_EXACT_RANGE_REQUIRED');
}

export function assertCurrentReplacementEntry(
  request: ReplacementRequest,
  entryId: string,
  current: SourceReplacementEntryResponse | undefined,
): void {
  const entry =
    request.entries.find((row) => row.entryId === entryId) ??
    fail('REPLACEMENT_ENTRY_NOT_SELECTED');
  const range = replacementRange(request, entryId);
  if (
    !current ||
    current.id !== entryId ||
    current.phase !== 'gap_open' ||
    current.revision !== entry.revision ||
    current.scopeDigest !== entry.digest ||
    current.sourceSha256 !== entry.sourceSha256 ||
    current.rangeStart !== range.sequenceStart ||
    current.rangeEnd !== range.sequenceEnd ||
    replacementCanonicalJson(current.sequenceNumbers) !==
      replacementCanonicalJson(entry.sequenceNumbers)
  )
    fail('REPLACEMENT_ENTRY_STALE');
}

export function createReplacementRepair(
  request: ReplacementRequest,
  repairKey: string,
  directoryName: string,
  now: string,
): ReplacementRepairManifest {
  return {
    schemaVersion: REPLACEMENT_REPAIR_SCHEMA,
    mode: 'source_replacement',
    repairKey,
    selectedDirectoryName: directoryName,
    request: parseReplacementRequest(request),
    revision: 0,
    journal: [],
    updatedAt: now,
  };
}

export function validateReplacementRepair(
  value: unknown,
): ReplacementRepairManifest {
  if (
    !object(value) ||
    value.schemaVersion !== REPLACEMENT_REPAIR_SCHEMA ||
    value.mode !== 'source_replacement' ||
    typeof value.repairKey !== 'string' ||
    !value.repairKey ||
    typeof value.selectedDirectoryName !== 'string' ||
    !value.selectedDirectoryName ||
    !Number.isSafeInteger(value.revision) ||
    (value.revision as number) < 0 ||
    typeof value.updatedAt !== 'string' ||
    !Array.isArray(value.journal)
  )
    return fail('REPLACEMENT_INVALID_MANIFEST');
  const manifest = value as unknown as ReplacementRepairManifest;
  parseReplacementRequest(manifest.request);
  const ids = new Set<string>();
  const entries = new Set<string>();
  let pending = 0;
  for (const write of manifest.journal) {
    if (
      !object(write) ||
      typeof write.id !== 'string' ||
      !write.id ||
      ids.has(write.id) ||
      typeof write.entryId !== 'string' ||
      entries.has(write.entryId) ||
      !sha(write.checksumSha256) ||
      !positive(write.size) ||
      typeof write.sourcePath !== 'string' ||
      !write.sourcePath ||
      (write.sourceIndex !== null &&
        (!Number.isSafeInteger(write.sourceIndex) || write.sourceIndex < 0)) ||
      typeof write.occurredAt !== 'string' ||
      !['intent', 'committed'].includes(write.state)
    )
      return fail('REPLACEMENT_INVALID_JOURNAL');
    validateReplacementTarget(manifest.request, write.entryId, write.fileName);
    if (
      manifest.request.entries.find((entry) => entry.entryId === write.entryId)
        ?.sourceSha256 === write.checksumSha256
    )
      fail('REPLACEMENT_RETIRED_SHA');
    ids.add(write.id);
    entries.add(write.entryId);
    if (write.state === 'intent') pending++;
  }
  if (pending > 1) fail('REPLACEMENT_MULTIPLE_PENDING');
  return manifest;
}

export function commitReplacementWrite(
  manifest: ReplacementRepairManifest,
  id: string,
  now: string,
): ReplacementRepairManifest {
  validateReplacementRepair(manifest);
  if (!manifest.journal.some((write) => write.id === id))
    fail('REPLACEMENT_UNKNOWN_OPERATION');
  return {
    ...manifest,
    revision: manifest.revision + 1,
    journal: manifest.journal.map((write) =>
      write.id === id ? { ...write, state: 'committed' } : write,
    ),
    updatedAt: now,
  };
}

/** Verification is supplied by the filesystem reader for this exact journal entry. */
export function deriveReplacementFilledGaps(
  manifest: ReplacementRepairManifest,
  verified: readonly {
    fileName: string;
    checksumSha256: string;
    size: number;
  }[],
): ManualSelectionFilledGapsManifest {
  validateReplacementRepair(manifest);
  const entries: ManualSelectionFilledGapEntry[] = [];
  for (const write of manifest.journal) {
    if (write.state !== 'committed') continue;
    if (
      !verified.some(
        (file) =>
          file.fileName === write.fileName &&
          file.checksumSha256 === write.checksumSha256 &&
          file.size === write.size,
      )
    )
      fail('REPLACEMENT_UNVERIFIED_COMMIT');
    const range = replacementRange(manifest.request, write.entryId);
    entries.push({
      fileName: write.fileName,
      start: range.sequenceStart,
      end: range.sequenceEnd,
      checksumSha256: write.checksumSha256,
      sourcePath: write.sourcePath,
      sourceIndex: write.sourceIndex,
      fillOperationId: write.id,
      filledAt: write.occurredAt,
    });
  }
  entries.sort((a, b) => a.start - b.start);
  return {
    schemaVersion: 'manual-image-selection-filled-gaps-v1',
    repairKey: manifest.repairKey,
    selectedDirectoryName: manifest.selectedDirectoryName,
    repairRevision: manifest.revision,
    entries,
    updatedAt: manifest.updatedAt,
  };
}

/** Local C2 descriptor, deliberately separate from both API payloads and filled-gaps-v1. */
export function deriveReplacementStagingSelection(
  manifest: ReplacementRepairManifest,
  verified: readonly {
    fileName: string;
    checksumSha256: string;
    size: number;
  }[],
  selectedEntryIds: readonly string[],
) {
  deriveReplacementFilledGaps(manifest, verified);
  if (
    !selectedEntryIds.length ||
    new Set(selectedEntryIds).size !== selectedEntryIds.length
  )
    fail('REPLACEMENT_INVALID_SELECTION');
  const files = selectedEntryIds.map((entryId) => {
    const write =
      manifest.journal.find(
        (row) => row.entryId === entryId && row.state === 'committed',
      ) ?? fail('REPLACEMENT_SELECTION_NOT_COMMITTED');
    const range = replacementRange(manifest.request, entryId);
    return {
      entryId,
      fileName: write.fileName,
      checksumSha256: write.checksumSha256,
      rangeStart: range.sequenceStart,
      rangeEnd: range.sequenceEnd,
      operationId: write.id,
    };
  });
  return {
    request: manifest.request,
    selectedEntryIds: [...selectedEntryIds],
    files,
  };
}
