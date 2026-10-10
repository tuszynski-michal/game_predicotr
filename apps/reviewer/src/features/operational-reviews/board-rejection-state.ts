import type {
  BoardCellGeometryRejectionCommand,
  OperationalImageReviewResolutionCommand,
} from '@game-predictor/admin-api-client';

/** Why an operator rejects a cropped board or a deferred slot (W7, D-543). */
export type BoardRejectionReason = 'blurred' | 'cropped' | 'other';

export const BOARD_REJECTION_REASONS: readonly {
  readonly label: string;
  readonly value: BoardRejectionReason;
}[] = [
  { label: 'Plansza przycięta', value: 'cropped' },
  { label: 'Rozmyta', value: 'blurred' },
  { label: 'Inny', value: 'other' },
];

/**
 * The note of a board rejection travels inside the 500-character reason text
 * of the resolution route (`other: <note>`), so it is capped below that.
 */
export const MAX_BOARD_REJECTION_NOTE_LENGTH = 400;

export interface BoardRejectionRequest {
  /** Fixed for one opening of the dialog: every retry replays it. */
  readonly idempotencyKey: string;
  readonly note: string;
  readonly reason: BoardRejectionReason;
}

export function boardRejectionReasonLabel(
  reason: string | null | undefined,
): string {
  return (
    BOARD_REJECTION_REASONS.find((entry) => entry.value === reason)?.label ??
    'Nie podano powodu'
  );
}

/** Empty when the draft may be sent; otherwise the Polish reason it may not. */
export function boardRejectionDraftError(
  reason: BoardRejectionReason | null,
  note: string,
): string {
  if (reason === null) return 'Wybierz powód odrzucenia.';
  const trimmed = note.trim();
  if (reason === 'other' && trimmed === '') {
    return 'Przy powodzie „Inny” opisz, dlaczego plansza jest odrzucana.';
  }
  if (trimmed.length > MAX_BOARD_REJECTION_NOTE_LENGTH) {
    return `Opis może mieć najwyżej ${MAX_BOARD_REJECTION_NOTE_LENGTH} znaków.`;
  }
  return '';
}

/** The note a request carries: only the reason "Inny" has one. */
export function boardRejectionNote(
  reason: BoardRejectionReason,
  note: string,
): string | null {
  return reason === 'other' ? note.trim() : null;
}

/** `cropped`, `blurred` or `other: <note>` — what the list decodes back. */
export function boardRejectionReasonText(
  reason: BoardRejectionReason,
  note: string,
): string {
  return reason === 'other' ? `other: ${note.trim()}` : reason;
}

export function slotRejectionCommand(
  request: BoardRejectionRequest,
  expectedGeometryRevision: number,
): BoardCellGeometryRejectionCommand {
  return {
    expectedGeometryRevision,
    idempotencyKey: request.idempotencyKey,
    note: boardRejectionNote(request.reason, request.note),
    reason: request.reason,
  };
}

export function boardRejectionCommand(
  request: BoardRejectionRequest,
  board: {
    readonly geometryRevision: number;
    readonly resolutionRevision: number;
  },
): OperationalImageReviewResolutionCommand {
  return {
    action: 'rejected',
    cells: [],
    expectedRevision: board.resolutionRevision,
    geometryRevision: board.geometryRevision,
    idempotencyKey: request.idempotencyKey,
    rejectionReason: boardRejectionReasonText(request.reason, request.note),
    resolvedBy: 'local-admin',
    sequenceNumber: null,
  };
}
