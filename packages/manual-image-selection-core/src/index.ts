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
  1, 2, 3, 4, 5, 6, 7, 10, 15, 20,
] as const;

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
    nextRangeStart: state.nextRangeStart + 9,
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
