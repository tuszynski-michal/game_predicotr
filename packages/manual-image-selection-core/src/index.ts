export type ManualDecisionAction = 'accepted' | 'skipped';

export interface ManualImageDescriptor {
  readonly name: string;
  readonly relativePath: string;
}

export interface ManualSelectionDecision {
  readonly action: ManualDecisionAction;
  readonly imagePath: string | null;
  readonly imageChecksum: string | null;
  readonly outputName: string | null;
  readonly rangeEnd: number;
  readonly rangeStart: number;
}

export type ManualSelectionTraceEventKind =
  'viewed' | 'accepted' | 'skipped' | 'undo';

export interface ManualSelectionTraceEvent {
  readonly eventIndex: number;
  readonly gameId: string;
  readonly sessionKey: string;
  readonly kind: ManualSelectionTraceEventKind;
  readonly rangeEnd: number;
  readonly rangeStart: number;
  readonly imagePath: string | null;
  readonly sourceIndex: number | null;
  readonly recordedAt: string;
  readonly visibleMilliseconds: number;
  readonly decoded: boolean;
  readonly imageChecksum?: string | null;
  readonly outputName?: string | null;
  readonly decisionOrdinal?: number | null;
  readonly revertsDecisionOrdinal?: number | null;
}

export interface ManualSelectionState {
  readonly currentIndex: number;
  readonly decisions: readonly ManualSelectionDecision[];
  readonly direction: 'ascending' | 'descending';
  readonly firstLayout: number;
  readonly navigationStep?: number;
  readonly nextRangeStart: number;
  readonly updatedAt: string;
}

export interface ManualSelectionSessionMetadata {
  readonly gameId: string;
  readonly key: string;
  readonly sourceDirectoryName: string;
  readonly state: ManualSelectionState;
}

export interface ManualSelectionOutputManifestV1 {
  readonly schemaVersion: 1;
  readonly gameId: string;
  readonly sessionKey: string;
  readonly sourceDirectoryName: string;
  readonly direction: 'ascending' | 'descending';
  readonly firstLayout: number;
  readonly updatedAt: string;
  readonly items: readonly {
    readonly outputName: string;
    readonly imagePath: string;
    readonly imageChecksum: string;
    readonly rangeStart: number;
    readonly rangeEnd: number;
  }[];
}

export interface ManualSelectionTraceManifestV1 {
  readonly schemaVersion: 1;
  readonly gameId: string;
  readonly sessionKey: string;
  readonly sourceDirectoryName: string;
  readonly direction: 'ascending' | 'descending';
  readonly firstLayout: number;
  readonly exportedAt: string;
  readonly events: readonly ManualSelectionTraceEvent[];
}

export interface ManualOutputFileResult {
  readonly checksum: string;
  readonly created: boolean;
  readonly name: string;
}

export interface ManualSelectionSourcePort<
  TImage extends ManualImageDescriptor,
> {
  listImages(): Promise<readonly TImage[]>;
}

export interface ManualSelectionOutputPort<
  TImage extends ManualImageDescriptor,
> {
  writeAcceptedOutput(
    source: TImage,
    rangeStart: number,
    rangeEnd: number,
    options?: { readonly allowReplace?: boolean },
  ): Promise<ManualOutputFileResult>;
  removeManagedOutput(decision: ManualSelectionDecision): Promise<void>;
  writeOutputManifest(record: ManualSelectionSessionMetadata): Promise<void>;
  writeTraceManifest(
    record: ManualSelectionSessionMetadata,
    events: readonly ManualSelectionTraceEvent[],
  ): Promise<void>;
}

export interface ManualSelectionSessionPort<TRecord> {
  loadIndependent(independentId: string): Promise<TRecord | null>;
  save(record: TRecord): Promise<void>;
  appendTraceEvent(event: ManualSelectionTraceEvent): Promise<void>;
  loadTraceEvents(
    gameId: string,
    sessionKey: string,
  ): Promise<ManualSelectionTraceEvent[]>;
}

const JPEG_EXTENSIONS = new Set(['.jpg', '.jpeg']);
const NATURAL_PARTS = /(\d+)/g;

export const INDEPENDENT_MANUAL_SELECTION_ID =
  'local-independent-manual-image-selection';

export const MANUAL_IMAGE_NAVIGATION_STEPS = [
  1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20,
] as const;

export type ManualSelectionShortcutAction =
  | 'accept'
  | 'skip'
  | 'undo'
  | 'previous_image'
  | 'next_image'
  | 'previous_step'
  | 'next_step';

export interface ManualSelectionKeyboardInput {
  readonly key: string;
  readonly altKey?: boolean;
  readonly ctrlKey?: boolean;
  readonly metaKey?: boolean;
  readonly repeat?: boolean;
  readonly target?: {
    readonly tagName?: string;
    readonly isContentEditable?: boolean;
  } | null;
}

export interface ManualImageSize {
  readonly height: number;
  readonly width: number;
}

export function fitManualImageToViewport(
  naturalSize: ManualImageSize | null,
  viewportSize: ManualImageSize | null,
  zoom: number,
): ManualImageSize | null {
  if (
    naturalSize === null ||
    viewportSize === null ||
    naturalSize.height < 1 ||
    naturalSize.width < 1 ||
    viewportSize.height < 1 ||
    viewportSize.width < 1 ||
    !Number.isFinite(zoom) ||
    zoom <= 0
  ) {
    return null;
  }
  const fitScale = Math.min(
    1,
    viewportSize.width / naturalSize.width,
    viewportSize.height / naturalSize.height,
  );
  return {
    height: Math.max(1, Math.round(naturalSize.height * fitScale * zoom)),
    width: Math.max(1, Math.round(naturalSize.width * fitScale * zoom)),
  };
}

export function resolveManualSelectionShortcut(
  input: ManualSelectionKeyboardInput,
): ManualSelectionShortcutAction | null {
  const tagName = input.target?.tagName?.toUpperCase();
  if (
    input.target?.isContentEditable === true ||
    tagName === 'BUTTON' ||
    tagName === 'INPUT' ||
    tagName === 'SELECT' ||
    tagName === 'TEXTAREA'
  ) {
    return null;
  }
  if (input.key === 'ArrowRight') return 'next_image';
  if (input.key === 'ArrowLeft') return 'previous_image';
  if (input.key === 'ArrowDown') return 'next_step';
  if (input.key === 'ArrowUp') return 'previous_step';
  if (input.key === 'Enter') return 'accept';
  if (input.key === 'Tab') return 'skip';
  const key = input.key.toLowerCase();
  if (
    key === 'f' &&
    input.ctrlKey !== true &&
    input.metaKey !== true &&
    input.altKey !== true &&
    input.repeat !== true
  ) {
    return 'accept';
  }
  if (
    key === 'a' &&
    input.ctrlKey !== true &&
    input.metaKey !== true &&
    input.altKey !== true &&
    input.repeat !== true
  ) {
    return 'undo';
  }
  if ((input.ctrlKey === true || input.metaKey === true) && key === 'z') {
    return 'undo';
  }
  return null;
}

export function isSupportedManualImage(name: string): boolean {
  const extension = name.slice(name.lastIndexOf('.')).toLowerCase();
  return JPEG_EXTENSIONS.has(extension);
}

export function naturalCompare(left: string, right: string): number {
  const leftParts = left.toLocaleLowerCase().split(NATURAL_PARTS);
  const rightParts = right.toLocaleLowerCase().split(NATURAL_PARTS);
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index] ?? '';
    const rightPart = rightParts[index] ?? '';
    const leftNumber = /^\d+$/.test(leftPart) ? Number(leftPart) : null;
    const rightNumber = /^\d+$/.test(rightPart) ? Number(rightPart) : null;
    if (
      leftNumber !== null &&
      rightNumber !== null &&
      leftNumber !== rightNumber
    ) {
      return leftNumber - rightNumber;
    }
    if (leftPart !== rightPart) return leftPart < rightPart ? -1 : 1;
  }
  return 0;
}

export function rangeForStart(rangeStart: number): {
  start: number;
  end: number;
} {
  return { end: rangeStart + 8, start: rangeStart };
}

export function nextManualRangeStart(
  direction: 'ascending' | 'descending',
  rangeStart: number,
): number {
  return direction === 'ascending'
    ? rangeStart + 9
    : Math.max(1, rangeStart - 9);
}

export function createManualSelectionState(
  firstLayout: number,
  direction: 'ascending' | 'descending',
): ManualSelectionState {
  return {
    currentIndex: 0,
    decisions: [],
    direction,
    firstLayout,
    navigationStep: 1,
    nextRangeStart: firstLayout,
    updatedAt: new Date().toISOString(),
  };
}

export function nextManualSelectionState(
  state: ManualSelectionState,
  decision: ManualSelectionDecision,
  currentIndex: number,
): ManualSelectionState {
  return {
    ...state,
    currentIndex,
    decisions: [...state.decisions, decision],
    nextRangeStart: nextManualRangeStart(state.direction, decision.rangeStart),
    updatedAt: new Date().toISOString(),
  };
}

export function previousManualSelectionState(
  state: ManualSelectionState,
): ManualSelectionState | null {
  const last = state.decisions.at(-1);
  if (last === undefined) return null;
  return {
    ...state,
    currentIndex: state.currentIndex,
    decisions: state.decisions.slice(0, -1),
    nextRangeStart: last.rangeStart,
    updatedAt: new Date().toISOString(),
  };
}

export function reconcileManualSelectionStateWithOutputManifest(
  state: ManualSelectionState,
  manifest: ManualSelectionOutputManifestV1,
): ManualSelectionState {
  if (manifest.direction !== state.direction) {
    throw new Error('Kierunek manifestu nie odpowiada zapisanej sesji.');
  }
  if (!Number.isSafeInteger(manifest.firstLayout) || manifest.firstLayout < 1) {
    throw new Error('Manifest ma nieprawidłowy pierwszy numer planszy.');
  }

  const accepted = state.decisions.filter(
    (decision) => decision.action === 'accepted',
  );
  if (accepted.length !== manifest.items.length) {
    throw new Error('Manifest nie odpowiada liczbie zatwierdzonych zdjęć.');
  }

  const offset = manifest.firstLayout - state.firstLayout;
  let acceptedIndex = 0;
  const decisions = state.decisions.map((decision) => {
    const oldRangeStart = decision.rangeStart;
    const oldRangeEnd = decision.rangeEnd;
    if (oldRangeEnd !== oldRangeStart + 8) {
      throw new Error('Zapisana sesja zawiera nieprawidłowy zakres decyzji.');
    }
    const rangeStart = oldRangeStart + offset;
    const rangeEnd = rangeStart + 8;
    if (decision.action === 'skipped') {
      return { ...decision, rangeEnd, rangeStart };
    }

    const item = manifest.items[acceptedIndex];
    acceptedIndex += 1;
    const outputName = `seq_${rangeStart}-${rangeEnd}.jpg`;
    if (
      item === undefined ||
      item.imageChecksum !== decision.imageChecksum ||
      item.imagePath !== decision.imagePath ||
      item.outputName !== outputName ||
      item.rangeStart !== rangeStart ||
      item.rangeEnd !== rangeEnd
    ) {
      throw new Error('Manifest nie odpowiada zapisanym plikom tej sesji.');
    }
    return { ...decision, outputName, rangeEnd, rangeStart };
  });

  return {
    ...state,
    decisions,
    firstLayout: manifest.firstLayout,
    nextRangeStart: state.nextRangeStart + offset,
    updatedAt: manifest.updatedAt,
  };
}

export function adjacentManualNavigationStep(
  value: number | undefined,
  direction: -1 | 1,
): number {
  const currentIndex = MANUAL_IMAGE_NAVIGATION_STEPS.includes(
    value as (typeof MANUAL_IMAGE_NAVIGATION_STEPS)[number],
  )
    ? MANUAL_IMAGE_NAVIGATION_STEPS.indexOf(
        value as (typeof MANUAL_IMAGE_NAVIGATION_STEPS)[number],
      )
    : 0;
  const nextIndex = Math.max(
    0,
    Math.min(
      MANUAL_IMAGE_NAVIGATION_STEPS.length - 1,
      currentIndex + direction,
    ),
  );
  return MANUAL_IMAGE_NAVIGATION_STEPS[nextIndex] ?? 1;
}

export function manualPreviewWindow(
  currentIndex: number,
  imageCount: number,
  radius = 3,
): readonly number[] {
  if (imageCount < 1 || currentIndex < 0 || currentIndex >= imageCount) {
    return [];
  }
  const boundedRadius = Math.max(0, Math.floor(radius));
  const first = Math.max(0, currentIndex - boundedRadius);
  const last = Math.min(imageCount - 1, currentIndex + boundedRadius);
  return Array.from({ length: last - first + 1 }, (_, index) => first + index);
}

export function createManualSelectionOutputManifest(
  record: ManualSelectionSessionMetadata,
  updatedAt = new Date().toISOString(),
): ManualSelectionOutputManifestV1 {
  const items = record.state.decisions
    .filter(
      (
        decision,
      ): decision is ManualSelectionDecision & {
        readonly imagePath: string;
        readonly imageChecksum: string;
        readonly outputName: string;
      } =>
        decision.action === 'accepted' &&
        decision.imagePath !== null &&
        decision.imageChecksum !== null &&
        decision.outputName !== null,
    )
    .map((decision) => ({
      imageChecksum: decision.imageChecksum,
      imagePath: decision.imagePath,
      outputName: decision.outputName,
      rangeEnd: decision.rangeEnd,
      rangeStart: decision.rangeStart,
    }));
  return {
    schemaVersion: 1,
    direction: record.state.direction,
    firstLayout: record.state.firstLayout,
    gameId: record.gameId,
    items,
    sessionKey: record.key,
    sourceDirectoryName: record.sourceDirectoryName,
    updatedAt,
  };
}

export function createManualSelectionTraceManifest(
  record: ManualSelectionSessionMetadata,
  events: readonly ManualSelectionTraceEvent[],
  exportedAt = new Date().toISOString(),
): ManualSelectionTraceManifestV1 {
  return {
    schemaVersion: 1,
    direction: record.state.direction,
    exportedAt,
    firstLayout: record.state.firstLayout,
    gameId: record.gameId,
    events,
    sessionKey: record.key,
    sourceDirectoryName: record.sourceDirectoryName,
  };
}

export const REMOTE_SOURCE_MANIFEST_SCHEMA =
  'remote-source-manifest-v1' as const;
export const REMOTE_SELECTION_MANIFEST_SCHEMA =
  'remote-manual-image-selection-session-v1' as const;
export const REMOTE_SELECTION_OPERATION_SCHEMA =
  'remote-manual-selection-operation-v1' as const;

export type RemoteManualSelectionSessionStatus =
  'draft' | 'active' | 'completed' | 'expired' | 'revoked';
export type RemoteManualSelectionCollectionStatus = 'active' | 'completed';
export type RemoteManualSelectionBatchStatus =
  | 'draft'
  | 'indexing'
  | 'active'
  | 'finalizing'
  | 'completed'
  | 'failed'
  | 'abandoned';
export type RemoteManualSelectionFileStatus =
  | 'discovered'
  | 'unselected'
  | 'selection_queued'
  | 'upload_queued'
  | 'uploading'
  | 'stored_temporarily'
  | 'verified'
  | 'materialized'
  | 'synced'
  | 'deselect_pending'
  | 'removed'
  | 'failed'
  | 'retrying';
export type RemoteManualSelectionOperationType =
  'viewed' | 'select' | 'skip' | 'deselect' | 'undo';
export type RemoteManualSelectionOperationStatus =
  | 'queued'
  | 'sending'
  | 'applied'
  | 'retry'
  | 'superseded'
  | 'conflict'
  | 'rejected';
export type RemoteManualSelectionTransferStatus =
  | 'queued'
  | 'uploading'
  | 'stored_temp'
  | 'verified'
  | 'materialized'
  | 'cancelled'
  | 'failed'
  | 'retrying';
export type RemoteManualSelectionHostActionType =
  'verify' | 'materialize' | 'remove' | 'reconcile';
export type RemoteManualSelectionHostActionStatus =
  'queued' | 'processing' | 'completed' | 'retry' | 'failed' | 'superseded';
export type RemoteManualSelectionDirection = 'ascending' | 'descending';
export type RemoteSourceKind = 'directory_handle' | 'webkitdirectory_reselect';

export interface RemoteSourceManifestEntryV1 {
  readonly ordinal: number;
  readonly relativePath: string;
  readonly name: string;
  readonly sizeBytes: number;
  readonly lastModifiedMs: number;
  readonly mimeType: string;
}

export interface RemoteSourceManifestV1 {
  readonly schemaVersion: typeof REMOTE_SOURCE_MANIFEST_SCHEMA;
  readonly sourceKind: RemoteSourceKind;
  readonly fileCount: number;
  readonly totalBytes: number;
  readonly entries: readonly RemoteSourceManifestEntryV1[];
  readonly manifestChecksumSha256: string;
}

export type RemoteSourceManifestComparison =
  | { readonly status: 'same'; readonly changedFileCount: 0 }
  | { readonly status: 'different'; readonly changedFileCount: number }
  | { readonly status: 'incompatible'; readonly changedFileCount: null };

export interface RemoteManualSelectionSessionV1 {
  readonly schemaVersion: 'remote-manual-selection-session-v1';
  readonly id: string;
  readonly status: RemoteManualSelectionSessionStatus;
  readonly revision: number;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly expiresAt: string;
}

export interface RemoteManualSelectionCollectionV1 {
  readonly schemaVersion: 'remote-manual-selection-collection-v1';
  readonly id: string;
  readonly sessionId: string;
  readonly name: string;
  readonly normalizedName: string;
  readonly status: RemoteManualSelectionCollectionStatus;
  readonly revision: number;
}

export interface RemoteManualSelectionBatchV1 {
  readonly schemaVersion: 'remote-manual-selection-batch-v1';
  readonly id: string;
  readonly sessionId: string;
  readonly collectionId: string;
  readonly name: string;
  readonly sourceManifestChecksumSha256: string;
  readonly firstLayout: number;
  readonly direction: RemoteManualSelectionDirection;
  readonly cursorIndex: number;
  readonly status: RemoteManualSelectionBatchStatus;
  readonly serverRevision: number;
  readonly lastClientSequence: number;
}

export interface RemoteManualSelectionFileV1 {
  readonly schemaVersion: 'remote-manual-selection-file-v1';
  readonly id: string;
  readonly sessionId: string;
  readonly batchId: string;
  readonly sourceIndex: number;
  readonly relativePath: string;
  readonly sizeBytes: number;
  readonly lastModifiedMs: number;
  readonly mimeType: string;
  readonly desiredSelected: boolean;
  readonly selectionGeneration: number;
  readonly status: RemoteManualSelectionFileStatus;
  readonly rangeStart: number | null;
  readonly rangeEnd: number | null;
  readonly outputName: string | null;
  readonly hostChecksumSha256: string | null;
}

export interface RemoteManualSelectionOperationCommandV1 {
  readonly schemaVersion: typeof REMOTE_SELECTION_OPERATION_SCHEMA;
  readonly operationId: string;
  readonly sessionId: string;
  readonly batchId: string;
  readonly clientInstanceId: string;
  readonly clientSequence: number;
  readonly expectedServerRevision: number;
  readonly operationType: RemoteManualSelectionOperationType;
  readonly selectionGeneration: number;
  readonly rangeStart: number;
  readonly rangeEnd: number;
  readonly recordedAt: string;
  readonly fileId: string | null;
  readonly imagePath: string | null;
  readonly sourceIndex: number | null;
  readonly imageChecksumSha256: string | null;
  readonly outputName: string | null;
  readonly visibleMilliseconds: number;
  readonly decoded: boolean;
  readonly targetOperationId: string | null;
}

export interface RemoteManualSelectionOperationV1 {
  readonly schemaVersion: 'remote-manual-selection-operation-result-v1';
  readonly command: RemoteManualSelectionOperationCommandV1;
  readonly commandChecksumSha256: string;
  readonly status: RemoteManualSelectionOperationStatus;
  readonly appliedServerRevision: number;
  readonly outcomeCode: string;
}

export interface RemoteManualSelectionTransferV1 {
  readonly schemaVersion: 'remote-manual-selection-transfer-v1';
  readonly id: string;
  readonly sessionId: string;
  readonly batchId: string;
  readonly fileId: string;
  readonly generation: number;
  readonly attempt: number;
  readonly declaredBytes: number;
  readonly receivedBytes: number;
  readonly status: RemoteManualSelectionTransferStatus;
  readonly declaredChecksumSha256: string | null;
  readonly verifiedChecksumSha256: string | null;
}

export interface RemoteManualSelectionHostActionV1 {
  readonly schemaVersion: 'remote-manual-selection-host-action-v1';
  readonly id: string;
  readonly sessionId: string;
  readonly batchId: string;
  readonly fileId: string;
  readonly transferId: string | null;
  readonly generation: number;
  readonly actionType: RemoteManualSelectionHostActionType;
  readonly status: RemoteManualSelectionHostActionStatus;
  readonly attempt: number;
}

export interface RemoteManualSelectionManifestV1 {
  readonly schemaVersion: typeof REMOTE_SELECTION_MANIFEST_SCHEMA;
  readonly sessionId: string;
  readonly collectionId: string;
  readonly batch: RemoteManualSelectionBatchV1;
  readonly files: readonly RemoteManualSelectionFileV1[];
  readonly operations: readonly RemoteManualSelectionOperationV1[];
  readonly transfers: readonly RemoteManualSelectionTransferV1[];
  readonly hostActions: readonly RemoteManualSelectionHostActionV1[];
  readonly generatedAt: string;
}

export class RemoteManualSelectionContractError extends Error {
  readonly code: string;
  readonly details: Readonly<Record<string, unknown>>;

  constructor(
    code: string,
    message: string,
    details: Readonly<Record<string, unknown>> = {},
  ) {
    super(message);
    this.name = 'RemoteManualSelectionContractError';
    this.code = code;
    this.details = details;
  }
}

export function normalizeRemoteSourcePath(value: string): string {
  const normalized = value.normalize('NFC');
  if (
    normalized.length === 0 ||
    normalized.includes('\0') ||
    normalized.includes('\\') ||
    normalized.startsWith('/') ||
    normalized.endsWith('/') ||
    /^[a-zA-Z]:/.test(normalized)
  ) {
    throw remoteSourceManifestError(
      'An absolute or malformed source path is not allowed.',
    );
  }
  const segments = normalized.split('/');
  if (
    segments.some(
      (segment) => segment.length === 0 || segment === '.' || segment === '..',
    )
  ) {
    throw remoteSourceManifestError(
      'A source path contains a forbidden segment.',
    );
  }
  return normalized;
}

export async function buildRemoteSourceManifestV1(
  values: readonly Omit<RemoteSourceManifestEntryV1, 'ordinal'>[],
  sourceKind: RemoteSourceKind,
): Promise<RemoteSourceManifestV1> {
  const entries = values
    .map((value) => {
      const relativePath = normalizeRemoteSourcePath(value.relativePath);
      const name = relativePath.split('/').at(-1);
      if (
        name === undefined ||
        name !== value.name ||
        !/\.jpe?g$/i.test(name) ||
        !Number.isSafeInteger(value.sizeBytes) ||
        value.sizeBytes < 0 ||
        !Number.isSafeInteger(value.lastModifiedMs) ||
        value.lastModifiedMs < 0
      ) {
        throw remoteSourceManifestError('Source metadata is invalid.');
      }
      return { ...value, relativePath };
    })
    .sort((left, right) =>
      naturalCompare(left.relativePath, right.relativePath),
    )
    .map((entry, ordinal) => ({ ordinal, ...entry }));
  const duplicate = entries.find(
    (entry, index) =>
      index > 0 && entry.relativePath === entries[index - 1]?.relativePath,
  );
  if (duplicate !== undefined) {
    throw remoteSourceManifestError('Source relative paths must be unique.');
  }
  const content = {
    schemaVersion: REMOTE_SOURCE_MANIFEST_SCHEMA,
    sourceKind,
    fileCount: entries.length,
    totalBytes: entries.reduce((total, entry) => total + entry.sizeBytes, 0),
    entries,
  };
  return {
    ...content,
    manifestChecksumSha256: await canonicalRemoteChecksumSha256(content),
  };
}

export function compareRemoteSourceManifestV1(
  expected: RemoteSourceManifestV1,
  candidate: RemoteSourceManifestV1,
): RemoteSourceManifestComparison {
  if (
    expected.schemaVersion !== REMOTE_SOURCE_MANIFEST_SCHEMA ||
    candidate.schemaVersion !== REMOTE_SOURCE_MANIFEST_SCHEMA ||
    expected.sourceKind !== candidate.sourceKind
  ) {
    return { changedFileCount: null, status: 'incompatible' };
  }
  if (expected.manifestChecksumSha256 === candidate.manifestChecksumSha256) {
    return { changedFileCount: 0, status: 'same' };
  }
  const expectedByPath = new Map(
    expected.entries.map((entry) => [entry.relativePath, entry]),
  );
  const candidateByPath = new Map(
    candidate.entries.map((entry) => [entry.relativePath, entry]),
  );
  const paths = new Set([...expectedByPath.keys(), ...candidateByPath.keys()]);
  let changedFileCount = 0;
  for (const path of paths) {
    const left = expectedByPath.get(path);
    const right = candidateByPath.get(path);
    if (
      left === undefined ||
      right === undefined ||
      left.sizeBytes !== right.sizeBytes ||
      left.lastModifiedMs !== right.lastModifiedMs ||
      left.mimeType !== right.mimeType
    ) {
      changedFileCount += 1;
    }
  }
  return { changedFileCount, status: 'different' };
}

export async function canonicalRemoteChecksumSha256(
  value: unknown,
): Promise<string> {
  const bytes = new TextEncoder().encode(stableRemoteStringify(value));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export function stableRemoteStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableRemoteStringify(item)).join(',')}]`;
  }
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value).sort(([left], [right]) =>
      left < right ? -1 : left > right ? 1 : 0,
    );
    return `{${entries
      .map(
        ([key, child]) =>
          `${JSON.stringify(key)}:${stableRemoteStringify(child)}`,
      )
      .join(',')}}`;
  }
  const serialized = JSON.stringify(value);
  if (serialized === undefined) {
    throw new RemoteManualSelectionContractError(
      'REMOTE_SELECTION_CONTRACT_INVALID',
      'The value cannot be represented in canonical JSON.',
    );
  }
  return serialized;
}

export function transitionRemoteSessionStatus(
  current: RemoteManualSelectionSessionStatus,
  target: RemoteManualSelectionSessionStatus,
): RemoteManualSelectionSessionStatus {
  return transitionRemoteStatus(
    current,
    target,
    REMOTE_SESSION_TRANSITIONS,
    'session',
  );
}

export function transitionRemoteBatchStatus(
  current: RemoteManualSelectionBatchStatus,
  target: RemoteManualSelectionBatchStatus,
): RemoteManualSelectionBatchStatus {
  return transitionRemoteStatus(
    current,
    target,
    REMOTE_BATCH_TRANSITIONS,
    'batch',
  );
}

export function transitionRemoteCollectionStatus(
  current: RemoteManualSelectionCollectionStatus,
  target: RemoteManualSelectionCollectionStatus,
): RemoteManualSelectionCollectionStatus {
  return transitionRemoteStatus(
    current,
    target,
    REMOTE_COLLECTION_TRANSITIONS,
    'collection',
  );
}

export function transitionRemoteFileStatus(
  current: RemoteManualSelectionFileStatus,
  target: RemoteManualSelectionFileStatus,
): RemoteManualSelectionFileStatus {
  return transitionRemoteStatus(
    current,
    target,
    REMOTE_FILE_TRANSITIONS,
    'file',
  );
}

export function transitionRemoteOperationStatus(
  current: RemoteManualSelectionOperationStatus,
  target: RemoteManualSelectionOperationStatus,
): RemoteManualSelectionOperationStatus {
  return transitionRemoteStatus(
    current,
    target,
    REMOTE_OPERATION_TRANSITIONS,
    'operation',
  );
}

export function transitionRemoteTransferStatus(
  current: RemoteManualSelectionTransferStatus,
  target: RemoteManualSelectionTransferStatus,
): RemoteManualSelectionTransferStatus {
  return transitionRemoteStatus(
    current,
    target,
    REMOTE_TRANSFER_TRANSITIONS,
    'transfer',
  );
}

export function transitionRemoteHostActionStatus(
  current: RemoteManualSelectionHostActionStatus,
  target: RemoteManualSelectionHostActionStatus,
): RemoteManualSelectionHostActionStatus {
  return transitionRemoteStatus(
    current,
    target,
    REMOTE_HOST_ACTION_TRANSITIONS,
    'hostAction',
  );
}

const REMOTE_SESSION_TRANSITIONS: Readonly<
  Partial<
    Record<
      RemoteManualSelectionSessionStatus,
      readonly RemoteManualSelectionSessionStatus[]
    >
  >
> = {
  draft: ['active', 'revoked'],
  active: ['completed', 'expired', 'revoked'],
};

const REMOTE_COLLECTION_TRANSITIONS: Readonly<
  Partial<
    Record<
      RemoteManualSelectionCollectionStatus,
      readonly RemoteManualSelectionCollectionStatus[]
    >
  >
> = {
  active: ['completed'],
};

const REMOTE_BATCH_TRANSITIONS: Readonly<
  Partial<
    Record<
      RemoteManualSelectionBatchStatus,
      readonly RemoteManualSelectionBatchStatus[]
    >
  >
> = {
  draft: ['indexing', 'abandoned'],
  indexing: ['active', 'failed', 'abandoned'],
  active: ['finalizing', 'failed', 'abandoned'],
  finalizing: ['completed', 'failed'],
  failed: ['indexing', 'active', 'finalizing', 'abandoned'],
};

const REMOTE_FILE_TRANSITIONS: Readonly<
  Partial<
    Record<
      RemoteManualSelectionFileStatus,
      readonly RemoteManualSelectionFileStatus[]
    >
  >
> = {
  discovered: ['unselected'],
  unselected: ['selection_queued'],
  selection_queued: ['upload_queued', 'deselect_pending', 'failed'],
  upload_queued: ['uploading', 'deselect_pending', 'failed'],
  uploading: ['stored_temporarily', 'deselect_pending', 'failed'],
  stored_temporarily: ['verified', 'deselect_pending', 'failed'],
  verified: ['materialized', 'deselect_pending', 'failed'],
  materialized: ['synced', 'deselect_pending', 'failed'],
  synced: ['deselect_pending'],
  deselect_pending: ['unselected', 'removed', 'selection_queued', 'failed'],
  removed: ['selection_queued'],
  failed: ['retrying', 'deselect_pending'],
  retrying: ['upload_queued', 'unselected', 'deselect_pending'],
};

const REMOTE_OPERATION_TRANSITIONS: Readonly<
  Partial<
    Record<
      RemoteManualSelectionOperationStatus,
      readonly RemoteManualSelectionOperationStatus[]
    >
  >
> = {
  queued: ['sending'],
  sending: ['applied', 'retry', 'superseded', 'conflict', 'rejected'],
  retry: ['sending'],
  applied: ['superseded'],
};

const REMOTE_TRANSFER_TRANSITIONS: Readonly<
  Partial<
    Record<
      RemoteManualSelectionTransferStatus,
      readonly RemoteManualSelectionTransferStatus[]
    >
  >
> = {
  queued: ['uploading', 'cancelled'],
  uploading: ['stored_temp', 'cancelled', 'failed'],
  stored_temp: ['verified', 'failed'],
  verified: ['materialized'],
  failed: ['retrying'],
  retrying: ['uploading', 'cancelled'],
};

const REMOTE_HOST_ACTION_TRANSITIONS: Readonly<
  Partial<
    Record<
      RemoteManualSelectionHostActionStatus,
      readonly RemoteManualSelectionHostActionStatus[]
    >
  >
> = {
  queued: ['processing', 'superseded'],
  processing: ['completed', 'retry', 'failed', 'superseded'],
  retry: ['processing'],
};

function transitionRemoteStatus<S extends string>(
  current: S,
  target: S,
  transitions: Readonly<Partial<Record<S, readonly S[]>>>,
  entity: string,
): S {
  if (current === target) return current;
  if (!transitions[current]?.includes(target)) {
    throw new RemoteManualSelectionContractError(
      'REMOTE_SELECTION_INVALID_TRANSITION',
      `The ${entity} transition is not allowed.`,
      { entity, from: current, to: target },
    );
  }
  return target;
}

function remoteSourceManifestError(
  message: string,
): RemoteManualSelectionContractError {
  return new RemoteManualSelectionContractError(
    'REMOTE_SELECTION_SOURCE_MANIFEST_INVALID',
    message,
  );
}
