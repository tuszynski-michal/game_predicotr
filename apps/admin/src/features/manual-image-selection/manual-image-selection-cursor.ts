import type {
  ManualImageDescriptor,
  ManualSelectionDecision,
  ManualSelectionTraceEvent,
} from '@game-predictor/manual-image-selection-core';

export type ManualSelectionCursorSemantics =
  'source_ordinal_v1' | 'source_path_v2';

export const MANUAL_SELECTION_CURSOR_SEMANTICS: ManualSelectionCursorSemantics =
  'source_path_v2';

type Direction = 'ascending' | 'descending';

export interface ResumeManualSelectionCursorInput {
  readonly cursorSemantics?: ManualSelectionCursorSemantics;
  readonly currentImagePath?: string;
  readonly currentIndex: number;
  readonly decisions: readonly ManualSelectionDecision[];
  readonly direction: Direction;
  readonly images: readonly ManualImageDescriptor[];
  readonly traceEvents: readonly ManualSelectionTraceEvent[];
}

export interface ResumedManualSelectionCursor {
  readonly currentIndex: number;
  readonly currentImagePath: string | null;
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
    // A viewed event is generated after the cursor has already been restored.
    // It therefore cannot prove the representation used by the historical
    // cursor and must not make an incorrect migration permanent.
    if (
      event.kind !== 'accepted' ||
      event.imagePath === null ||
      event.sourceIndex === null
    ) {
      continue;
    }
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

function cursorAfterLastAcceptedDecision(
  decisions: readonly ManualSelectionDecision[],
  images: readonly ManualImageDescriptor[],
  direction: Direction,
): number | null {
  const accepted = [...decisions]
    .reverse()
    .find(
      (decision): decision is ManualSelectionDecision & { imagePath: string } =>
        decision.action === 'accepted' && decision.imagePath !== null,
    );
  if (accepted === undefined) return null;
  const sourceIndex = images.findIndex(
    (image) => image.relativePath === accepted.imagePath,
  );
  if (sourceIndex < 0) return null;
  return moveManualSelectionCursor(sourceIndex, direction, images.length, 1);
}

function imagePathAt(
  images: readonly ManualImageDescriptor[],
  currentIndex: number,
): string | null {
  return images[currentIndex]?.relativePath ?? null;
}

export function resumeManualSelectionCursor(
  input: ResumeManualSelectionCursorInput,
): ResumedManualSelectionCursor {
  const currentIndex = clampCursorIndex(
    input.currentIndex,
    input.images.length,
  );
  if (input.currentImagePath !== undefined) {
    const sourceIndex = input.images.findIndex(
      (image) => image.relativePath === input.currentImagePath,
    );
    if (sourceIndex < 0) {
      throw new Error('MANUAL_SELECTION_CURSOR_IMAGE_MISSING');
    }
    return {
      currentIndex: sourceIndex,
      currentImagePath: input.currentImagePath,
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      migratedLegacyCursor: false,
    };
  }

  // v0.8.59 could have marked a descending legacy record as source-ordinal
  // after restoring it from an index alone. A completed decision contains a
  // stable source path, so it is a stronger anchor than either old index
  // representation. Skipped decisions intentionally keep this same image.
  const decisionCursor =
    input.direction === 'descending'
      ? cursorAfterLastAcceptedDecision(
          input.decisions,
          input.images,
          input.direction,
        )
      : null;
  if (decisionCursor !== null) {
    return {
      currentIndex: decisionCursor,
      currentImagePath: imagePathAt(input.images, decisionCursor),
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      migratedLegacyCursor: true,
    };
  }

  if (input.cursorSemantics === MANUAL_SELECTION_CURSOR_SEMANTICS) {
    return {
      currentIndex,
      currentImagePath: imagePathAt(input.images, currentIndex),
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      migratedLegacyCursor: false,
    };
  }
  if (input.cursorSemantics === 'source_ordinal_v1') {
    return {
      currentIndex,
      currentImagePath: imagePathAt(input.images, currentIndex),
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      migratedLegacyCursor: true,
    };
  }
  if (input.direction === 'ascending') {
    return {
      currentIndex,
      currentImagePath: imagePathAt(input.images, currentIndex),
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
    currentImagePath: imagePathAt(
      input.images,
      legacyOrder === 'natural'
        ? currentIndex
        : input.images.length - 1 - currentIndex,
    ),
    cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
    migratedLegacyCursor: true,
  };
}
