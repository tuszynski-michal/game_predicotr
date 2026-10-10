import type {
  BoardSearchBoardCellResponse,
  SymbolCellReviewMutationRequest,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from './api-error.ts';
import type {
  BoardSearchDataSource,
  BoardSearchEditableCell,
  BoardSearchCorrectionContext,
} from './board-search-data-source.ts';

/**
 * Cell correction from the board payline modal (D-473). A correction is the
 * same checksum-bound human decision as in "Weryfikacja symboli": it goes
 * through `applySymbolCellReviewDecision`, so search and every payout see
 * the corrected symbol at once (D-462).
 */

export type BoardCellCorrectionChoice =
  | { readonly kind: 'symbol'; readonly symbolCode: string }
  | { readonly kind: 'unreadable' }
  | { readonly kind: 'grid_issue' };

export type BoardCellCorrectionClient = Pick<
  BoardSearchDataSource,
  'applySymbolCellReviewDecision' | 'correctBoardSearchCell'
>;

/**
 * The request for one choice: the currently assigned symbol confirms the
 * cell (`approve`), another symbol rewrites it (`reassign`). `null` when the
 * chosen symbol is not part of the game catalogue.
 */
export function boardCellCorrectionRequest(
  cell: BoardSearchBoardCellResponse,
  choice: BoardCellCorrectionChoice,
  symbols: readonly SymbolResponse[],
): SymbolCellReviewMutationRequest | null {
  const expected = {
    expectedCropChecksumSha256: cell.cropChecksumSha256,
    expectedCropSampleId: cell.cropSampleId,
    expectedGeometryRevision: cell.geometryRevision,
    expectedRevision: cell.revision,
  };
  if (choice.kind === 'unreadable') {
    return { ...expected, action: 'mark_unreadable' };
  }
  if (choice.kind === 'grid_issue') {
    return { ...expected, action: 'mark_grid_issue' };
  }
  const symbol = symbols.find((item) => item.code === choice.symbolCode);
  if (symbol === undefined) return null;
  if (cell.assignedSymbolCode === choice.symbolCode) {
    return { ...expected, action: 'approve' };
  }
  return { ...expected, action: 'reassign', targetSymbolId: symbol.id };
}

/** Symbols offered in the correction palette: active ones, catalogue order. */
export function boardCellCorrectionPalette(
  symbols: readonly SymbolResponse[],
): readonly SymbolResponse[] {
  return symbols
    .filter((symbol) => symbol.status === 'active')
    .sort(
      (left, right) =>
        left.displayOrder - right.displayOrder ||
        left.mobileCode - right.mobileCode ||
        left.id.localeCompare(right.id),
    );
}

export type BoardCellCorrectionResult =
  | { readonly ok: true }
  | {
      readonly ok: false;
      readonly error: string;
      /** The cell changed since it was read (revision or crop drift). */
      readonly conflict: boolean;
    };

const CONFLICT_CODES: ReadonlySet<string> = new Set([
  'SYMBOL_CELL_REVIEW_REVISION_CONFLICT',
  'SYMBOL_CELL_REVIEW_CROP_DRIFT',
  'BOARD_SEARCH_SHARE_CORRECTION_CONFLICT',
]);

export async function applyBoardCellCorrection(
  api: BoardCellCorrectionClient,
  gameId: string,
  cell: BoardSearchEditableCell,
  choice: BoardCellCorrectionChoice,
  symbols: readonly SymbolResponse[],
  sequenceNumber?: number,
  context?: BoardSearchCorrectionContext,
): Promise<BoardCellCorrectionResult> {
  if (
    choice.kind === 'symbol' &&
    !symbols.some((item) => item.code === choice.symbolCode)
  ) {
    return {
      conflict: false,
      error: 'Wybrany symbol nie należy do tej gry.',
      ok: false,
    };
  }
  try {
    let result: { readonly data?: unknown; readonly error?: unknown };
    if ('cellVersion' in cell) {
      if (
        api.correctBoardSearchCell === undefined ||
        sequenceNumber === undefined
      ) {
        return {
          ok: false,
          conflict: false,
          error: 'Zapis symboli nie jest dostępny.',
        };
      }
      const action =
        choice.kind === 'unreadable'
          ? 'mark_unreadable'
          : choice.kind === 'grid_issue'
            ? 'mark_grid_issue'
            : cell.assignedSymbolCode === choice.symbolCode &&
                cell.qualityIssue === null
              ? 'approve'
              : 'reassign';
      result = await api.correctBoardSearchCell(
        gameId,
        sequenceNumber,
        cell.cellIndex,
        {
          ...context,
          expectedCellVersion: cell.cellVersion,
          action,
          ...(action === 'reassign' && choice.kind === 'symbol'
            ? { targetSymbolCode: choice.symbolCode }
            : {}),
        },
      );
    } else {
      const request = boardCellCorrectionRequest(cell, choice, symbols);
      if (request === null || api.applySymbolCellReviewDecision === undefined) {
        return {
          ok: false,
          conflict: false,
          error: 'Zapis symboli nie jest dostępny.',
        };
      }
      result = await api.applySymbolCellReviewDecision(
        gameId,
        cell.cellReviewId,
        request,
      );
    }
    if (result.error !== undefined || result.data === undefined) {
      const code =
        typeof result.error === 'object' &&
        result.error !== null &&
        'code' in result.error &&
        typeof result.error.code === 'string'
          ? result.error.code
          : null;
      return {
        conflict: code !== null && CONFLICT_CODES.has(code),
        error: apiErrorMessage(
          result.error,
          'Nie udało się zapisać poprawki pola.',
        ),
        ok: false,
      };
    }
    return { ok: true };
  } catch {
    return {
      conflict: false,
      error:
        'Połączenie zostało przerwane. Ponów ten sam wybór, aby sprawdzić zapis.',
      ok: false,
    };
  }
}
