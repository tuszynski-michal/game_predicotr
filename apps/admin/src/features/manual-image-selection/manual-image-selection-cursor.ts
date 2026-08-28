import type {
  ManualImageDescriptor,
  ManualSelectionTraceEvent,
} from '@game-predictor/manual-image-selection-core';

export type ManualSelectionCursorSemantics = 'source_ordinal_v1';

export const MANUAL_SELECTION_CURSOR_SEMANTICS: ManualSelectionCursorSemantics =
  'source_ordinal_v1';

type Direction = 'ascending' | 'descending';

export interface ResumeManualSelectionCursorInput {
  readonly cursorSemantics?: ManualSelectionCursorSemantics;
  readonly currentIndex: number;
  readonly direction: Direction;
  readonly images: readonly ManualImageDescriptor[];
  readonly traceEvents: readonly ManualSelectionTraceEvent[];
}

export interface ResumedManualSelectionCursor {
  readonly currentIndex: number;
  readonly cursorSemantics: ManualSelectionCursorSemantics;
  readonly migratedLegacyCursor: boolean;
}

function clampCursorIndex(index: number, imageCount: number): number {
  if (imageCount === 0) return 0;
  return Math.max(0, Math.min(imageCount - 1, index));
}

export function initialManualSelectionCursor(
  direction: Direction,
  imageCount: number,
): number {
  if (imageCount === 0) return 0;
  return direction === 'ascending' ? 0 : imageCount - 1;
}

export function moveManualSelectionCursor(
  currentIndex: number,
  direction: Direction,
  imageCount: number,
  selectionDelta: number,
): number {
  const sourceDelta =
    direction === 'ascending' ? selectionDelta : -selectionDelta;
  return clampCursorIndex(currentIndex + sourceDelta, imageCount);
}

export function manualSelectionDisplayPosition(
  currentIndex: number,
  direction: Direction,
  imageCount: number,
): number {
  if (imageCount === 0) return 0;
  const sourceIndex = clampCursorIndex(currentIndex, imageCount);
  return direction === 'ascending' ? sourceIndex + 1 : imageCount - sourceIndex;
}

function legacyCursorOrderFromTrace(
  images: readonly ManualImageDescriptor[],
  traceEvents: readonly ManualSelectionTraceEvent[],
): 'natural' | 'reversed' | null {
  const newestFirst = [...traceEvents].sort(
    (left, right) => right.eventIndex - left.eventIndex,
  );
  for (const event of newestFirst) {
    if (event.imagePath === null || event.sourceIndex === null) continue;
    const naturalIndex = images.findIndex(
      (image) => image.relativePath === event.imagePath,
    );
    if (naturalIndex < 0) continue;
    const reversedIndex = images.length - 1 - naturalIndex;
    if (
      event.sourceIndex === naturalIndex &&
      event.sourceIndex !== reversedIndex
    ) {
      return 'natural';
    }
    if (
      event.sourceIndex === reversedIndex &&
      event.sourceIndex !== naturalIndex
    ) {
      return 'reversed';
    }
  }
  return null;
}

export function resumeManualSelectionCursor(
  input: ResumeManualSelectionCursorInput,
): ResumedManualSelectionCursor {
  const currentIndex = clampCursorIndex(
    input.currentIndex,
    input.images.length,
  );
  if (input.cursorSemantics === MANUAL_SELECTION_CURSOR_SEMANTICS) {
    return {
      currentIndex,
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      migratedLegacyCursor: false,
    };
  }
  if (input.direction === 'ascending') {
    return {
      currentIndex,
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      migratedLegacyCursor: true,
    };
  }

  const legacyOrder = legacyCursorOrderFromTrace(
    input.images,
    input.traceEvents,
  );
  return {
    currentIndex:
      legacyOrder === 'natural'
        ? currentIndex
        : input.images.length - 1 - currentIndex,
    cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
    migratedLegacyCursor: true,
  };
}
